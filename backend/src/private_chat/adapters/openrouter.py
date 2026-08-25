from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from private_chat.adapters.usage import parse_generation_usage, parse_openrouter_usage
from private_chat.domain.models import ModelRequest, ModelResponse
from private_chat.ports.interfaces import ModelProviderError


class OpenRouterConfiguration(BaseModel):
    """Privacy controls are required data, not optional call-site flags."""

    model_config = ConfigDict(frozen=True)
    api_key: SecretStr
    allowed_providers: tuple[str, ...] = Field(min_length=1)
    allowed_provider_names: tuple[str, ...] | None = Field(default=None, min_length=1)
    base_url: str = "https://openrouter.ai/api/v1"
    zero_data_retention: bool = True
    max_output_tokens: int = Field(default=4096, ge=1, le=4096)

    @field_validator("base_url")
    @classmethod
    def require_https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("OpenRouter must use HTTPS")
        return value.rstrip("/")

    @field_validator("zero_data_retention")
    @classmethod
    def require_zdr(cls, value: bool) -> bool:
        if not value:
            raise ValueError("OpenRouter zero-data-retention cannot be disabled")
        return value


class OpenRouterModelClient:
    """OpenRouter adapter that fails closed if privacy guarantees cannot be verified."""

    def __init__(self, config: OpenRouterConfiguration, client: httpx.AsyncClient) -> None:
        self._config = config
        self._client = client

    async def generate(self, request: ModelRequest) -> ModelResponse:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
            "provider": {
                "order": list(self._config.allowed_providers),
                # `only` is the hard filter; `order` makes selection deterministic within it.
                "only": list(self._config.allowed_providers),
                "allow_fallbacks": False,
                "data_collection": "deny",
                "zdr": True,
            },
            "max_tokens": self._config.max_output_tokens,
        }
        response = await self._client.post(
            f"{self._config.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._config.api_key.get_secret_value()}"},
            json=payload,
        )
        try:
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPStatusError, ValueError) as exc:
            raise ModelProviderError("OpenRouter request failed") from exc
        if not isinstance(body, Mapping):
            raise ModelProviderError("OpenRouter returned an invalid response")
        provider = body.get("provider")
        # Routing uses endpoint slugs (for example ``google-vertex``), while the
        # completion response uses provider display names (for example ``Google``).
        # Keep both allowlists explicit rather than comparing unlike identifiers.
        provider_names = self._config.allowed_provider_names or self._config.allowed_providers
        if not isinstance(provider, str) or provider not in provider_names:
            raise ModelProviderError("OpenRouter response did not confirm an allowed provider")
        try:
            content = body["choices"][0]["message"]["content"]
            model = body["model"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelProviderError("OpenRouter returned an invalid response") from exc
        if not isinstance(content, str) or not content.strip() or not isinstance(model, str):
            raise ModelProviderError("OpenRouter returned an invalid response")
        usage = parse_openrouter_usage(body.get("usage"), model=model, provider=provider)
        if usage is None:
            generation_id = response.headers.get("x-generation-id") or body.get("id")
            if isinstance(generation_id, str) and generation_id:
                generation_response = await self._client.get(
                    f"{self._config.base_url}/generation",
                    headers={"Authorization": f"Bearer {self._config.api_key.get_secret_value()}"},
                    params={"id": generation_id},
                )
                if generation_response.is_success:
                    usage = parse_generation_usage(
                        generation_response.json(), model=model, provider=provider
                    )
        return ModelResponse(content=content, model=model, provider=provider, usage=usage)

    async def verify_zdr_route(self, model_id: str) -> None:
        """Fail startup if OpenRouter no longer publishes this exact ZDR route."""

        response = await self._client.get("https://openrouter.ai/api/v1/endpoints/zdr")
        response.raise_for_status()
        body = response.json()
        entries = body.get("data") if isinstance(body, Mapping) else None
        if not isinstance(entries, list):
            raise RuntimeError("OpenRouter returned an invalid ZDR endpoint catalogue")
        allowed = set(self._config.allowed_providers)
        provider_names = set(self._config.allowed_provider_names or self._config.allowed_providers)
        for entry in entries:
            if not isinstance(entry, Mapping) or entry.get("model_id") != model_id:
                continue
            tag = entry.get("tag")
            provider = str(tag).split("/", 1)[0] if isinstance(tag, str) else ""
            if (
                provider in allowed
                and entry.get("provider_name") in provider_names
                and entry.get("status", 0) == 0
            ):
                return
        raise RuntimeError(
            "No configured OpenRouter provider currently offers a verified ZDR route for "
            + model_id
        )
