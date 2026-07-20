"""Framework-independent objects used by the application's business logic.

These types deliberately use standard-library dataclasses rather than Pydantic.
Untrusted input is validated at the API and configuration boundaries before it
is converted into these small, immutable domain values.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class Role(StrEnum):
    """The speaker represented by a message sent to or received from a model."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


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
