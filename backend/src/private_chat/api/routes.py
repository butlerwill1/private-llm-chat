from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from private_chat.api.schemas import HealthResponse, MessageResponse, SendMessageRequest
from private_chat.application.send_message import SendMessage, SendMessageCommand

router = APIRouter()


def get_send_message(request: Request) -> SendMessage:
    return cast(SendMessage, request.app.state.send_message)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse)
async def send_message(
    conversation_id: UUID,
    body: SendMessageRequest,
    use_case: Annotated[SendMessage, Depends(get_send_message)],
) -> MessageResponse:
    # Never log `body`: it contains plaintext user content.
    result = await use_case.execute(
        SendMessageCommand(
            conversation_id=conversation_id,
            content=body.content,
            model=body.model,
        )
    )
    return MessageResponse.from_domain(result)
