from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from private_chat.domain.models import ModelRequest, ModelResponse


class OpenRouterConfiguration(BaseModel):
    """Privacy controls are required data, not optional call-site flags."""

    model_config = ConfigDict(frozen=True)
    api_key: SecretStr
    allowed_providers: tuple[str, ...] = Field(min_length=1)
    base_url: str = "https://openrouter.ai/api/v1"
    zero_data_retention: bool = True

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
        }
        response = await self._client.post(
            f"{self._config.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._config.api_key.get_secret_value()}"},
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, Mapping):
            raise RuntimeError("OpenRouter returned an invalid response")
        provider = body.get("provider")
        # A missing provider cannot prove that the allow-list was honoured, so it is rejected.
        if not isinstance(provider, str) or provider not in self._config.allowed_providers:
            raise RuntimeError("OpenRouter response did not confirm an allowed provider")
        try:
            content = body["choices"][0]["message"]["content"]
            model = body["model"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("OpenRouter returned an invalid response") from exc
        if not isinstance(content, str) or not content.strip() or not isinstance(model, str):
            raise RuntimeError("OpenRouter returned an invalid response")
        return ModelResponse(content=content, model=model, provider=provider)
