"""Pydantic schemas at the untrusted HTTP boundary.

FastAPI uses these models to validate JSON, serialise responses and generate the
OpenAPI contract. They are kept separate from the domain dataclasses so transport
rules do not leak into the business layer.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from private_chat.domain.models import ChatMessage, Role


class SendMessageRequest(BaseModel):
    """Validated JSON body accepted by the send-message endpoint."""

    # Reject misspelled or unexpected fields rather than silently ignoring them.
    model_config = ConfigDict(extra="forbid")
    # Limits provide an early guard against empty input and unbounded request bodies.
    content: str = Field(min_length=1, max_length=32_000)
    model: str = Field(min_length=1, max_length=200)


class MessageResponse(BaseModel):
    """Public representation returned after an assistant message is completed."""

    id: UUID
    role: Role
    content: str
    created_at: datetime

    @classmethod
    def from_domain(cls, message: ChatMessage) -> "MessageResponse":
        """Map a domain object to the API contract without exposing internals."""

        return cls(
            id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
        )


class HealthResponse(BaseModel):
    """Small response used by health checks without touching conversation data."""

    status: str
