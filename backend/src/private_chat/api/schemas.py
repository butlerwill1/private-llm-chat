"""Pydantic schemas at the untrusted HTTP boundary.

FastAPI uses these models to validate JSON, serialise responses and generate the
OpenAPI contract. They are kept separate from the domain dataclasses so transport
rules do not leak into the business layer.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from private_chat.application.conversations import ConversationView
from private_chat.domain.models import ChatMessage, Conversation, Role


class SendMessageRequest(BaseModel):
    """Validated JSON body accepted by the send-message endpoint."""

    # Reject misspelled or unexpected fields rather than silently ignoring them.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    # Limits provide an early guard against empty input and unbounded request bodies.
    content: str = Field(min_length=1, max_length=32_000)
    model_id: str | None = Field(default=None, min_length=1, max_length=200)


class ModelOptionResponse(BaseModel):
    """A browser-safe configured model choice with no provider credentials."""

    id: str
    label: str
    backend: str


class ModelConfigurationResponse(BaseModel):
    """Non-secret controls that determine which model IDs the browser may submit."""

    custom_openrouter_model_allowed: bool


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


class ConversationResponse(BaseModel):
    """Complete conversation contract consumed by the local React application."""

    id: UUID
    title: str
    created_at: datetime
    messages: tuple[MessageResponse, ...]

    @classmethod
    def from_view(cls, view: ConversationView) -> "ConversationResponse":
        return cls(
            id=view.conversation.id,
            title=view.conversation.title,
            created_at=view.conversation.created_at,
            messages=tuple(MessageResponse.from_domain(message) for message in view.messages),
        )


class ConversationSummaryResponse(BaseModel):
    """Metadata required for navigation, intentionally excluding messages."""

    id: UUID
    title: str
    created_at: datetime

    @classmethod
    def from_domain(cls, conversation: Conversation) -> "ConversationSummaryResponse":
        return cls(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
        )


class HealthResponse(BaseModel):
    """Small response used by health checks without touching conversation data."""

    status: str
