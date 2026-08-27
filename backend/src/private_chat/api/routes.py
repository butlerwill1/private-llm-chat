from typing import Annotated, cast
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from private_chat.api.schemas import (
    ChangeModelRequest,
    ConversationResponse,
    ConversationSummaryResponse,
    CreateConversationRequest,
    HealthResponse,
    ModelConfigurationResponse,
    ModelOptionResponse,
    RenameConversationRequest,
    SendMessageRequest,
)
from private_chat.application.conversations import ConversationService
from private_chat.application.model_router import ConfiguredModelCatalog, ModelOption
from private_chat.application.send_message import SendMessage, SendMessageCommand
from private_chat.ports.interfaces import ModelProviderError

router = APIRouter()


def get_send_message(request: Request) -> SendMessage:
    return cast(SendMessage, request.app.state.send_message)


def get_conversations(request: Request) -> ConversationService:
    return cast(ConversationService, request.app.state.conversations)


def get_model_options(request: Request) -> tuple[ModelOption, ...]:
    return cast(tuple[ModelOption, ...], request.app.state.model_options)


def get_model_catalog(request: Request) -> ConfiguredModelCatalog:
    return cast(ConfiguredModelCatalog, request.app.state.model_catalog)


def get_custom_model_allowed(request: Request) -> bool:
    return cast(bool, request.app.state.custom_openrouter_model_allowed)


def get_model_backend(request: Request) -> str:
    return cast(str, request.app.state.model_backend)


def get_storage_label(request: Request) -> str:
    return cast(str, request.app.state.storage_label)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/models", response_model=tuple[ModelOptionResponse, ...])
async def list_models(
    options: Annotated[tuple[ModelOption, ...], Depends(get_model_options)],
) -> tuple[ModelOptionResponse, ...]:
    """Return only the approved model catalogue for this local session."""

    return tuple(
        ModelOptionResponse(
            id=item.id,
            label=item.label,
            backend=item.backend,
            provider=item.provider,
            available=item.available,
        )
        for item in options
    )


@router.get("/model-configuration", response_model=ModelConfigurationResponse)
async def model_configuration(
    custom_model_allowed: Annotated[bool, Depends(get_custom_model_allowed)],
    model_backend: Annotated[str, Depends(get_model_backend)],
    storage_label: Annotated[str, Depends(get_storage_label)],
) -> ModelConfigurationResponse:
    """Tell the browser whether typed OpenRouter model IDs are enabled locally."""

    return ModelConfigurationResponse(
        custom_openrouter_model_allowed=custom_model_allowed,
        model_backend=model_backend,
        storage_label=storage_label,
    )


@router.get("/conversations", response_model=tuple[ConversationResponse, ...])
async def list_conversations(
    service: Annotated[ConversationService, Depends(get_conversations)],
    catalog: Annotated[ConfiguredModelCatalog, Depends(get_model_catalog)],
) -> tuple[ConversationResponse, ...]:
    views = await service.list()
    return tuple(ConversationResponse.from_view(view, catalog) for view in views)


@router.get("/conversation-summaries", response_model=tuple[ConversationSummaryResponse, ...])
async def list_conversation_summaries(
    service: Annotated[ConversationService, Depends(get_conversations)],
) -> tuple[ConversationSummaryResponse, ...]:
    """Return navigation metadata without loading encrypted message content."""

    return tuple(
        ConversationSummaryResponse.from_domain(conversation)
        for conversation in await service.list_metadata()
    )


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    service: Annotated[ConversationService, Depends(get_conversations)],
    catalog: Annotated[ConfiguredModelCatalog, Depends(get_model_catalog)],
    body: CreateConversationRequest | None = None,
) -> ConversationResponse:
    try:
        return ConversationResponse.from_view(
            await service.create(None if body is None else body.model_id), catalog
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    service: Annotated[ConversationService, Depends(get_conversations)],
    catalog: Annotated[ConfiguredModelCatalog, Depends(get_model_catalog)],
) -> ConversationResponse:
    view = await service.get(conversation_id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return ConversationResponse.from_view(view, catalog)


@router.patch("/conversations/{conversation_id}/model", response_model=ConversationResponse)
async def change_model(
    conversation_id: UUID,
    body: ChangeModelRequest,
    service: Annotated[ConversationService, Depends(get_conversations)],
    catalog: Annotated[ConfiguredModelCatalog, Depends(get_model_catalog)],
) -> ConversationResponse:
    try:
        return ConversationResponse.from_view(
            await service.change_model(conversation_id, body.model_id), catalog
        )
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


@router.patch("/conversations/{conversation_id}/title", response_model=ConversationResponse)
async def rename_conversation(
    conversation_id: UUID,
    body: RenameConversationRequest,
    service: Annotated[ConversationService, Depends(get_conversations)],
    catalog: Annotated[ConfiguredModelCatalog, Depends(get_model_catalog)],
) -> ConversationResponse:
    try:
        return ConversationResponse.from_view(
            await service.rename(conversation_id, body.title), catalog
        )
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    service: Annotated[ConversationService, Depends(get_conversations)],
) -> Response:
    if not await service.delete(conversation_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/conversations/{conversation_id}/messages", response_model=ConversationResponse)
async def send_message(
    conversation_id: UUID,
    body: SendMessageRequest,
    use_case: Annotated[SendMessage, Depends(get_send_message)],
    service: Annotated[ConversationService, Depends(get_conversations)],
    catalog: Annotated[ConfiguredModelCatalog, Depends(get_model_catalog)],
) -> ConversationResponse:
    # Never log `body`: it contains plaintext user content.
    try:
        await use_case.execute(
            SendMessageCommand(
                conversation_id=conversation_id,
                content=body.content,
            )
        )
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        ) from error
    except httpx.TimeoutException as error:
        # A local model can need time to generate, but a finite timeout still
        # protects the browser from a permanently broken tunnel or model service.
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The local model did not respond before the inference timeout.",
        ) from error
    except ModelProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The selected model provider returned an unusable response. Please try again.",
        ) from error
    view = await service.get(conversation_id)
    if view is None:
        raise RuntimeError("Conversation disappeared after a completed turn")
    return ConversationResponse.from_view(view, catalog)
