"""Configured model selection without exposing provider credentials to callers."""

from collections.abc import Mapping
from dataclasses import dataclass

from private_chat.domain.models import ModelRequest, ModelResponse
from private_chat.ports.interfaces import ModelClient


@dataclass(frozen=True, slots=True)
class ModelOption:
    """A safe model choice returned to the local browser."""

    id: str
    label: str
    backend: str
    provider: str | None = None


class ModelRouter:
    """Select a preconfigured inference client by an approved model identifier."""

    def __init__(
        self,
        clients: Mapping[str, ModelClient],
        *,
        custom_openrouter_client: ModelClient | None = None,
        allow_custom_openrouter_model: bool = False,
    ) -> None:
        if not clients:
            raise ValueError("At least one configured model is required")
        self._clients = dict(clients)
        self._custom_openrouter_client = custom_openrouter_client
        self._allow_custom_openrouter_model = allow_custom_openrouter_model

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Route only to a configured client; reject unknown browser input."""

        try:
            client = self._clients[request.model]
        except KeyError as error:
            if self._allow_custom_openrouter_model and self._custom_openrouter_client is not None:
                return await self._custom_openrouter_client.generate(request)
            raise ValueError("The requested model is not enabled for this session") from error
        return await client.generate(request)
