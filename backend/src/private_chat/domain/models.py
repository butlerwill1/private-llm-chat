from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str
    id: UUID
    created_at: datetime

    @classmethod
    def create(cls, role: Role, content: str) -> "ChatMessage":
        if not content.strip():
            raise ValueError("Message content must not be blank")
        return cls(role=role, content=content, id=uuid4(), created_at=datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ModelRequest:
    messages: tuple[ChatMessage, ...]
    model: str


@dataclass(frozen=True, slots=True)
class ModelResponse:
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
    id: UUID
    conversation_id: UUID
    role: Role
    encrypted_content: EncryptedPayload
    created_at: datetime

