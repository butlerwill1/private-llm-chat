"""Framework-independent objects used by the application's business logic.

These types deliberately use standard-library dataclasses rather than Pydantic.
Untrusted input is validated at the API and configuration boundaries before it
is converted into these small, immutable domain values.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4


class Role(StrEnum):
    """The speaker represented by a message sent to or received from a model."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class CostBasis(StrEnum):
    """How a turn's monetary amount was obtained."""

    PROVIDER_REPORTED = "provider_reported"
    SELF_HOSTED_UNALLOCATED = "self_hosted_unallocated"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class TurnUsage:
    """Provider usage for one request, shared by its user and assistant messages."""

    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cached_input_tokens: int | None
    cache_write_input_tokens: int | None
    reasoning_tokens: int | None
    cost_usd: Decimal | None
    cost_basis: CostBasis
    model: str
    provider: str

    def __post_init__(self) -> None:
        for value in (
            self.input_tokens,
            self.output_tokens,
            self.total_tokens,
            self.cached_input_tokens,
            self.cache_write_input_tokens,
            self.reasoning_tokens,
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError("Token counts must be non-negative integers")
        if self.cost_usd is not None and self.cost_usd < 0:
            raise ValueError("Cost must be non-negative")
        if self.cost_basis is CostBasis.PROVIDER_REPORTED and self.cost_usd is None:
            raise ValueError("Provider-reported usage requires a cost")
        if self.cost_basis is not CostBasis.PROVIDER_REPORTED and self.cost_usd is not None:
            raise ValueError("Only provider-reported usage may carry a cost")

    @classmethod
    def unavailable(cls, *, model: str, provider: str) -> "TurnUsage":
        return cls(None, None, None, None, None, None, None, CostBasis.UNAVAILABLE, model, provider)


@dataclass(frozen=True, slots=True)
class Conversation:
    """Stable metadata for one encrypted transcript.

    Titles are user-managed metadata and are never inferred from transcript
    content. Persistence adapters envelope-encrypt them separately from messages.
    """

    id: UUID
    title: str
    created_at: datetime
    active_model_id: str | None = None

    @classmethod
    def create(
        cls, title: str = "New conversation", *, active_model_id: str | None = None
    ) -> "Conversation":
        """Create a conversation after enforcing the domain's title invariant."""

        cleaned_title = title.strip()
        if not cleaned_title:
            raise ValueError("Conversation title must not be blank")
        return cls(
            id=uuid4(),
            title=cleaned_title,
            created_at=datetime.now(UTC),
            active_model_id=active_model_id,
        )

    def renamed(self, title: str) -> "Conversation":
        """Return the same conversation with a validated, user-supplied title."""

        cleaned_title = title.strip()
        if not cleaned_title:
            raise ValueError("Conversation title must not be blank")
        if len(cleaned_title) > 200:
            raise ValueError("Conversation title must be 200 characters or fewer")
        return Conversation(
            id=self.id,
            title=cleaned_title,
            created_at=self.created_at,
            active_model_id=self.active_model_id,
        )


def conversation_title_context(conversation_id: UUID) -> bytes:
    """Bind a title ciphertext to one conversation and its metadata field."""

    return f"conversation={conversation_id};field=title".encode()


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One plaintext message while it is being processed in trusted memory.

    ``frozen=True`` prevents accidental mutation after construction. ``slots=True``
    makes the permitted attributes explicit and avoids a per-instance ``__dict__``.
    Stored messages use :class:`StoredMessage` instead so plaintext is not persisted.
    """

    role: Role
    content: str
    id: UUID
    created_at: datetime
    usage: TurnUsage | None = None

    @classmethod
    def create(cls, role: Role, content: str) -> "ChatMessage":
        """Create a new message with its identity and UTC timestamp supplied safely.

        ``cls`` is the class on which this factory was called. Using it instead of
        spelling ``ChatMessage`` directly also allows subclasses to reuse the factory.
        """

        if not content.strip():
            raise ValueError("Message content must not be blank")
        return cls(role=role, content=content, id=uuid4(), created_at=datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """Provider-neutral input passed through the ``ModelClient`` interface."""

    # A tuple communicates that an adapter must not alter the assembled context.
    messages: tuple[ChatMessage, ...]
    model: str


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """Normalised model output returned regardless of the selected provider."""

    content: str
    model: str
    provider: str
    usage: TurnUsage | None = None


@dataclass(frozen=True, slots=True)
class EncryptedPayload:
    """Ciphertext plus everything needed to unwrap its one-time data key.

    The data key itself must never be stored in this object.
    """

    ciphertext: bytes
    nonce: bytes
    wrapped_data_key: bytes
    key_id: str
    algorithm: str = "AES-256-GCM"


@dataclass(frozen=True, slots=True)
class StoredMessage:
    """Persistence representation containing encrypted content, never plaintext."""

    id: UUID
    conversation_id: UUID
    role: Role
    encrypted_content: EncryptedPayload
    created_at: datetime
