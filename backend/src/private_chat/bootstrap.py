from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from private_chat.adapters.encryption import AesGcmEnvelopeEncryptor, LocalAesDataKeyProvider
from private_chat.adapters.memory_repository import InMemoryConversationRepository
from private_chat.adapters.openrouter import OpenRouterConfiguration, OpenRouterModelClient
from private_chat.adapters.self_hosted import SelfHostedConfiguration, SelfHostedModelClient
from private_chat.api.routes import router
from private_chat.application.send_message import SendMessage
from private_chat.config import ModelBackend, Settings
from private_chat.ports.interfaces import ModelClient


def create_app(
    settings: Settings,
    *,
    http_client: httpx.AsyncClient | None = None,
    model_client: ModelClient | None = None,
) -> FastAPI:
    """Composition root: the only place concrete adapters are selected and wired."""

    owned_client: httpx.AsyncClient | None = None
    if model_client is None and http_client is None:
        owned_client = httpx.AsyncClient(timeout=httpx.Timeout(60))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if owned_client is not None:
                await owned_client.aclose()

    app = FastAPI(
        title="Private AWS Chatbot API",
        version="0.1.0",
        # Swagger remains useful locally, but a deployment should put all routes behind auth.
        docs_url="/docs" if settings.environment == "development" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    if model_client is None:
        client = http_client or owned_client
        if client is None:  # Defensive invariant for future composition changes.
            raise RuntimeError("HTTP client was not configured")
        if settings.model_backend == ModelBackend.OPENROUTER:
            if settings.openrouter_api_key is None:
                raise ValueError("CHAT_OPENROUTER_API_KEY is required for OpenRouter")
            model_client = OpenRouterModelClient(
                OpenRouterConfiguration(
                    api_key=settings.openrouter_api_key,
                    allowed_providers=settings.openrouter_allowed_providers,
                ),
                client,
            )
        else:
            model_client = SelfHostedModelClient(
                SelfHostedConfiguration(
                    base_url=settings.self_hosted_base_url,
                    api_key=settings.self_hosted_api_key,
                ),
                client,
            )
    repository = InMemoryConversationRepository()
    encryptor = AesGcmEnvelopeEncryptor(
        LocalAesDataKeyProvider(settings.local_master_key())
    )
    app.state.send_message = SendMessage(repository, encryptor, model_client)
    app.state.repository = repository
    app.include_router(router, prefix="/v1")
    return app
