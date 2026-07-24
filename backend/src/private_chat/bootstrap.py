from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import boto3
import httpx
from fastapi import FastAPI

from private_chat.adapters.aws_kms import KmsDataKeyProvider
from private_chat.adapters.encryption import AesGcmEnvelopeEncryptor, LocalAesDataKeyProvider
from private_chat.adapters.memory_repository import InMemoryConversationRepository
from private_chat.adapters.openrouter import OpenRouterConfiguration, OpenRouterModelClient
from private_chat.adapters.s3_repository import S3ConversationRepository
from private_chat.adapters.self_hosted import SelfHostedConfiguration, SelfHostedModelClient
from private_chat.api.routes import router
from private_chat.application.conversations import ConversationService
from private_chat.application.send_message import SendMessage
from private_chat.config import ModelBackend, Settings, StorageBackend
from private_chat.ports.interfaces import (
    ConversationRepository,
    DataKeyProvider,
    ModelClient,
)


def create_app(
    settings: Settings,
    *,
    http_client: httpx.AsyncClient | None = None,
    model_client: ModelClient | None = None,
) -> FastAPI:
    """Composition root: the only place concrete adapters are selected and wired."""

    owned_client: httpx.AsyncClient | None = None
    if model_client is None and http_client is None:
        # Connect failures should be reported quickly, while a local model is
        # allowed several minutes to generate a complete response.
        owned_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10,
                read=settings.model_response_timeout_seconds,
                write=30,
                pool=10,
            ),
            # The self-hosted endpoint is a loopback tunnel. Inheriting desktop
            # proxy configuration could route that private request through a
            # proxy or make it fail despite the tunnel being healthy.
            trust_env=settings.model_backend is ModelBackend.OPENROUTER,
        )

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
    repository: ConversationRepository
    data_keys: DataKeyProvider
    if settings.storage_backend is StorageBackend.S3:
        if settings.conversation_bucket is None or settings.kms_key_id is None:
            raise RuntimeError("Validated AWS storage settings are unexpectedly missing")
        repository = S3ConversationRepository(
            boto3.client("s3", region_name=settings.aws_region),
            settings.conversation_bucket,
            settings.kms_key_id,
        )
        data_keys = KmsDataKeyProvider(
            boto3.client("kms", region_name=settings.aws_region), settings.kms_key_id
        )
    else:
        repository = InMemoryConversationRepository()
        data_keys = LocalAesDataKeyProvider(settings.local_master_key())

    encryptor = AesGcmEnvelopeEncryptor(data_keys)
    app.state.send_message = SendMessage(
        repository, encryptor, model_client, settings.model_name
    )
    app.state.conversations = ConversationService(repository, encryptor)
    app.include_router(router, prefix="/v1")
    return app
