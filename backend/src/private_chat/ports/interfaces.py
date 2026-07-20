from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from private_chat.domain.models import (
    EncryptedPayload,
    ModelRequest,
    ModelResponse,
    StoredMessage,
)


class ModelClient(Protocol):
    async def generate(self, request: ModelRequest) -> ModelResponse: ...


class ConversationRepository(Protocol):
    async def list_messages(self, conversation_id: UUID) -> Sequence[StoredMessage]: ...

    async def append_turn(
        self, conversation_id: UUID, user: StoredMessage, assistant: StoredMessage
    ) -> None: ...


class EnvelopeEncryptor(Protocol):
    def encrypt(self, plaintext: bytes, *, context: bytes) -> EncryptedPayload: ...

    def decrypt(self, payload: EncryptedPayload, *, context: bytes) -> bytes: ...


class DataKeyProvider(Protocol):
    """Boundary implemented by AWS KMS in production and a local adapter in tests."""

    def generate_data_key(self, *, context: bytes) -> tuple[bytes, bytes, str]: ...

    def unwrap_data_key(
        self, wrapped_data_key: bytes, *, key_id: str, context: bytes
    ) -> bytes: ...

