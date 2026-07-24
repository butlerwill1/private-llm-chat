from typing import Annotated, cast
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from private_chat.api.schemas import (
    ConversationResponse,
    ConversationSummaryResponse,
    HealthResponse,
    ModelConfigurationResponse,
    ModelOptionResponse,
    SendMessageRequest,
)
from private_chat.application.conversations import ConversationService
from private_chat.application.model_router import ModelOption
from private_chat.application.send_message import SendMessage, SendMessageCommand

router = APIRouter()


def get_send_message(request: Request) -> SendMessage:
    return cast(SendMessage, request.app.state.send_message)


def get_conversations(request: Request) -> ConversationService:
    return cast(ConversationService, request.app.state.conversations)


def get_model_options(request: Request) -> tuple[ModelOption, ...]:
    return cast(tuple[ModelOption, ...], request.app.state.model_options)


def get_custom_model_allowed(request: Request) -> bool:
    return cast(bool, request.app.state.custom_openrouter_model_allowed)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/models", response_model=tuple[ModelOptionResponse, ...])
async def list_models(
    options: Annotated[tuple[ModelOption, ...], Depends(get_model_options)],
) -> tuple[ModelOptionResponse, ...]:
    """Return only the approved model catalogue for this local session."""

    return tuple(
        ModelOptionResponse(id=item.id, label=item.label, backend=item.backend)
        for item in options
    )


@router.get("/model-configuration", response_model=ModelConfigurationResponse)
async def model_configuration(
    custom_model_allowed: Annotated[bool, Depends(get_custom_model_allowed)],
) -> ModelConfigurationResponse:
    """Tell the browser whether typed OpenRouter model IDs are enabled locally."""

    return ModelConfigurationResponse(custom_openrouter_model_allowed=custom_model_allowed)


@router.get("/conversations", response_model=tuple[ConversationResponse, ...])
async def list_conversations(
    service: Annotated[ConversationService, Depends(get_conversations)],
) -> tuple[ConversationResponse, ...]:
    views = await service.list()
    return tuple(ConversationResponse.from_view(view) for view in views)


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
) -> ConversationResponse:
    return ConversationResponse.from_view(await service.create())


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    service: Annotated[ConversationService, Depends(get_conversations)],
) -> ConversationResponse:
    view = await service.get(conversation_id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return ConversationResponse.from_view(view)


@router.delete(
    "/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT
)
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
) -> ConversationResponse:
    # Never log `body`: it contains plaintext user content.
    try:
        await use_case.execute(
            SendMessageCommand(
                conversation_id=conversation_id,
                content=body.content,
                model_id=body.model_id,
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
    view = await service.get(conversation_id)
    if view is None:
        raise RuntimeError("Conversation disappeared after a completed turn")
    return ConversationResponse.from_view(view)
