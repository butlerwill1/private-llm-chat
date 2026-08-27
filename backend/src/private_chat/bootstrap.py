import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import boto3
import httpx
from fastapi import FastAPI

from private_chat.adapters.aws_kms import KmsDataKeyProvider
from private_chat.adapters.conversation_instructions import FileConversationInstructionsProvider
from private_chat.adapters.encryption import AesGcmEnvelopeEncryptor, LocalAesDataKeyProvider
from private_chat.adapters.memory_repository import InMemoryConversationRepository
from private_chat.adapters.openrouter import OpenRouterConfiguration, OpenRouterModelClient
from private_chat.adapters.s3_repository import S3ConversationRepository
from private_chat.adapters.self_hosted import SelfHostedConfiguration, SelfHostedModelClient
from private_chat.adapters.sqlite_repository import SqliteConversationRepository
from private_chat.adapters.windows_dpapi import DpapiLocalDataKeyProvider
from private_chat.api.routes import router
from private_chat.application.conversations import ConversationService
from private_chat.application.model_router import ConfiguredModelCatalog, ModelOption, ModelRouter
from private_chat.application.send_message import SendMessage
from private_chat.config import LocalKeyMode, ModelBackend, Settings, StorageBackend
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

    openrouter_clients: dict[str, OpenRouterModelClient] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            if settings.openrouter_zdr_preflight:
                await asyncio.gather(
                    *(
                        client.verify_zdr_route(model_id)
                        for model_id, client in openrouter_clients.items()
                    )
                )
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
    model_options: tuple[ModelOption, ...]
    if model_client is None:
        client = http_client or owned_client
        if client is None:  # Defensive invariant for future composition changes.
            raise RuntimeError("HTTP client was not configured")
        configured_clients: dict[str, ModelClient] = {}
        if settings.model_backend is ModelBackend.SELF_HOSTED:
            configured_clients[settings.model_name] = SelfHostedModelClient(
                SelfHostedConfiguration(
                    base_url=settings.self_hosted_base_url,
                    api_key=settings.self_hosted_api_key,
                ),
                client,
            )
        openrouter: OpenRouterModelClient | None = None
        if settings.enable_openrouter or settings.model_backend is ModelBackend.OPENROUTER:
            if settings.openrouter_api_key is None:
                raise RuntimeError("Validated OpenRouter key is unexpectedly missing")
            for route in settings.openrouter_routes:
                route_client = OpenRouterModelClient(
                    OpenRouterConfiguration(
                        api_key=settings.openrouter_api_key,
                        allowed_providers=(route.provider,),
                        allowed_provider_names=(route.provider_name,),
                        max_output_tokens=settings.openrouter_max_output_tokens,
                    ),
                    client,
                )
                configured_clients[route.model_id] = route_client
                openrouter_clients[route.model_id] = route_client
                openrouter = openrouter or route_client
        model_client = ModelRouter(
            configured_clients,
            custom_openrouter_client=openrouter,
            allow_custom_openrouter_model=settings.allow_custom_openrouter_model,
        )
        model_options = tuple(
            [ModelOption(settings.model_name, "Private GPU (Ollama)", "self_hosted")]
            if settings.model_backend is ModelBackend.SELF_HOSTED
            else []
        ) + tuple(
            ModelOption(route.model_id, route.label, "openrouter", route.provider)
            for route in (settings.openrouter_routes if settings.enable_openrouter else ())
        )
    else:
        model_options = (ModelOption(settings.model_name, settings.model_name, "test"),)
    data_keys: DataKeyProvider
    if settings.storage_backend is StorageBackend.S3:
        if settings.conversation_bucket is None or settings.kms_key_id is None:
            raise RuntimeError("Validated AWS storage settings are unexpectedly missing")
        data_keys = KmsDataKeyProvider(
            boto3.client("kms", region_name=settings.aws_region), settings.kms_key_id
        )
    elif settings.storage_backend is StorageBackend.MEMORY:
        data_keys = LocalAesDataKeyProvider(settings.local_master_key())
    else:
        data_directory = settings.resolved_local_data_dir()
        database_path = data_directory / "conversations.sqlite3"
        data_keys = (
            DpapiLocalDataKeyProvider.load_or_create(data_directory, database_path=database_path)
            if settings.local_key_mode is LocalKeyMode.DPAPI
            else LocalAesDataKeyProvider(settings.local_master_key())
        )
    encryptor = AesGcmEnvelopeEncryptor(data_keys)
    repository: ConversationRepository
    if settings.storage_backend is StorageBackend.S3:
        if settings.conversation_bucket is None or settings.kms_key_id is None:
            raise RuntimeError("Validated AWS storage settings are unexpectedly missing")
        repository = S3ConversationRepository(
            boto3.client("s3", region_name=settings.aws_region),
            settings.conversation_bucket,
            settings.kms_key_id,
            encryptor,
        )
    elif settings.storage_backend is StorageBackend.MEMORY:
        repository = InMemoryConversationRepository(encryptor)
    else:
        repository = SqliteConversationRepository(database_path, encryptor)
    catalog = ConfiguredModelCatalog(model_options)
    instructions_provider = FileConversationInstructionsProvider(settings.instructions_file)
    app.state.send_message = SendMessage(
        repository, encryptor, model_client, settings.model_name, instructions_provider
    )
    app.state.conversations = ConversationService(
        repository, encryptor, catalog, settings.model_name
    )
    app.state.model_options = catalog.list_models()
    app.state.model_catalog = catalog
    app.state.custom_openrouter_model_allowed = settings.allow_custom_openrouter_model
    app.state.model_backend = settings.model_backend.value
    app.state.storage_label = (
        "Encrypted local database"
        if settings.storage_backend is StorageBackend.LOCAL
        else "Envelope encrypted S3"
        if settings.storage_backend is StorageBackend.S3
        else "Encrypted in-memory session"
    )
    app.include_router(router, prefix="/v1")
    return app
