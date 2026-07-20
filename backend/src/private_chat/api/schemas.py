from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from private_chat.domain.models import ChatMessage, Role


class SendMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=32_000)
    model: str = Field(min_length=1, max_length=200)


class MessageResponse(BaseModel):
    id: UUID
    role: Role
    content: str
    created_at: datetime

    @classmethod
    def from_domain(cls, message: ChatMessage) -> "MessageResponse":
        return cls(
            id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
        )


class HealthResponse(BaseModel):
    status: str

