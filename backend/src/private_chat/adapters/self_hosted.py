import ipaddress
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from private_chat.adapters.usage import parse_self_hosted_usage
from private_chat.domain.models import ModelRequest, ModelResponse


class SelfHostedConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)
    base_url: str = "http://127.0.0.1:11434/v1"
    api_key: SecretStr | None = None

    @field_validator("base_url")
    @classmethod
    def require_private_endpoint(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
            raise ValueError("A valid model endpoint is required")
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError as exc:
            message = "Use an explicit private or loopback IP for the model endpoint"
            raise ValueError(message) from exc
        if not (address.is_private or address.is_loopback):
            raise ValueError("Self-hosted model endpoint must not be public")
        return value.rstrip("/")


class SelfHostedModelClient:
    """Adapter for an OpenAI-compatible endpoint such as vLLM or Ollama's v1 API."""

    def __init__(self, config: SelfHostedConfiguration, client: httpx.AsyncClient) -> None:
        self._config = config
        self._client = client

    async def generate(self, request: ModelRequest) -> ModelResponse:
        headers = {}
        if self._config.api_key is not None:
            headers["Authorization"] = f"Bearer {self._config.api_key.get_secret_value()}"
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
        }
        response = await self._client.post(
            f"{self._config.base_url}/chat/completions", headers=headers, json=payload
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, Mapping):
            raise RuntimeError("Model server returned an invalid response")
        try:
            content = body["choices"][0]["message"]["content"]
            model = body["model"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Model server returned an invalid response") from exc
        if not isinstance(content, str) or not content.strip() or not isinstance(model, str):
            raise RuntimeError("Model server returned an invalid response")
        return ModelResponse(
            content=content,
            model=model,
            provider="self-hosted",
            usage=parse_self_hosted_usage(body.get("usage"), model=model, provider="self-hosted"),
        )
