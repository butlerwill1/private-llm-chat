"""Interfaces owned by the application and implemented by external adapters.

``Protocol`` provides structural typing: an implementation does not need to inherit
from these classes; it only needs to supply methods with compatible signatures.
This keeps application services independent of OpenRouter, AWS and local test doubles.
"""

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
    """Port shared by hosted and self-hosted inference adapters."""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate one normalised response from provider-neutral input."""

        ...


class ConversationRepository(Protocol):
    """Encrypted conversation persistence required by application use cases."""

    async def list_messages(self, conversation_id: UUID) -> Sequence[StoredMessage]:
        """Return stored messages in their authoritative conversation order."""

        ...

    async def append_turn(
        self, conversation_id: UUID, user: StoredMessage, assistant: StoredMessage
    ) -> None:
        """Persist both sides of a completed turn atomically."""

        ...


class EnvelopeEncryptor(Protocol):
    """Application-level authenticated encryption boundary."""

    def encrypt(self, plaintext: bytes, *, context: bytes) -> EncryptedPayload:
        """Encrypt bytes while cryptographically binding them to their context."""

        ...

    def decrypt(self, payload: EncryptedPayload, *, context: bytes) -> bytes:
        """Authenticate and decrypt a payload for the expected context."""

        ...


class DataKeyProvider(Protocol):
    """Create and unwrap one-time data keys without owning payload encryption.

    AWS KMS implements this boundary in production; a local adapter keeps unit tests
    fast and deterministic without pretending to provide a production key service.
    """

    def generate_data_key(self, *, context: bytes) -> tuple[bytes, bytes, str]:
        """Return plaintext key material, its wrapped form and the wrapping-key ID."""

        ...

    def unwrap_data_key(self, wrapped_data_key: bytes, *, key_id: str, context: bytes) -> bytes:
        """Recover data-key bytes only when key identity and context are authorised."""

        ...
