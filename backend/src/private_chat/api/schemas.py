"""Pydantic schemas at the untrusted HTTP boundary.

FastAPI uses these models to validate JSON, serialise responses and generate the
OpenAPI contract. They are kept separate from the domain dataclasses so transport
rules do not leak into the business layer.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from private_chat.adapters.telemetry import SystemMonitorSnapshot
from private_chat.application.conversations import ConversationView
from private_chat.application.model_router import ConfiguredModelCatalog
from private_chat.domain.models import ChatMessage, Conversation, CostBasis, Role, TurnUsage


class SendMessageRequest(BaseModel):
    """Validated JSON body accepted by the send-message endpoint."""

    # Reject misspelled or unexpected fields rather than silently ignoring them.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    # Limits provide an early guard against empty input and unbounded request bodies.
    content: str = Field(min_length=1, max_length=32_000)


class CreateConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str | None = Field(default=None, min_length=1, max_length=200)


class ChangeModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=1, max_length=200)


class RenameConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)


class ModelOptionResponse(BaseModel):
    """A browser-safe configured model choice with no provider credentials."""

    id: str
    label: str
    backend: str
    provider: str | None = None
    available: bool = True


class ModelConfigurationResponse(BaseModel):
    """Non-secret controls that determine which model IDs the browser may submit."""

    custom_openrouter_model_allowed: bool
    model_backend: str
    storage_label: str


class TurnUsageResponse(BaseModel):
    """Request-level usage repeated on both messages in a completed turn."""

    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cached_input_tokens: int | None
    cache_write_input_tokens: int | None
    reasoning_tokens: int | None
    cost_usd: str | None
    cost_basis: CostBasis
    model: str
    model_label: str
    provider: str

    @classmethod
    def from_domain(cls, usage: TurnUsage, catalog: ConfiguredModelCatalog) -> "TurnUsageResponse":
        label = next(
            (option.label for option in catalog.list_models() if option.id == usage.model),
            usage.model,
        )
        return cls(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            cache_write_input_tokens=usage.cache_write_input_tokens,
            reasoning_tokens=usage.reasoning_tokens,
            cost_usd=None if usage.cost_usd is None else str(usage.cost_usd),
            cost_basis=usage.cost_basis,
            model=usage.model,
            model_label=label,
            provider=usage.provider,
        )


class MessageResponse(BaseModel):
    """Public representation returned after an assistant message is completed."""

    id: UUID
    role: Role
    content: str
    created_at: datetime
    usage: TurnUsageResponse | None

    @classmethod
    def from_domain(
        cls, message: ChatMessage, catalog: ConfiguredModelCatalog
    ) -> "MessageResponse":
        """Map a domain object to the API contract without exposing internals."""

        return cls(
            id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
            usage=None
            if message.usage is None
            else TurnUsageResponse.from_domain(message.usage, catalog),
        )


class ConversationResponse(BaseModel):
    """Complete conversation contract consumed by the local React application."""

    id: UUID
    title: str
    created_at: datetime
    active_model_id: str | None
    messages: tuple[MessageResponse, ...]

    @classmethod
    def from_view(
        cls, view: ConversationView, catalog: ConfiguredModelCatalog
    ) -> "ConversationResponse":
        return cls(
            id=view.conversation.id,
            title=view.conversation.title,
            created_at=view.conversation.created_at,
            active_model_id=view.conversation.active_model_id,
            messages=tuple(
                MessageResponse.from_domain(message, catalog) for message in view.messages
            ),
        )


class ConversationSummaryResponse(BaseModel):
    """Metadata required for navigation, intentionally excluding messages."""

    id: UUID
    title: str
    created_at: datetime
    active_model_id: str | None

    @classmethod
    def from_domain(cls, conversation: Conversation) -> "ConversationSummaryResponse":
        return cls(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            active_model_id=conversation.active_model_id,
        )


class HealthResponse(BaseModel):
    """Small response used by health checks without touching conversation data."""

    status: str


class TelemetryStatusResponse(BaseModel):
    sample_count: int
    database_bytes: int


class SystemMonitorResponse(BaseModel):
    snapshot: SystemMonitorSnapshot
    telemetry: TelemetryStatusResponse
