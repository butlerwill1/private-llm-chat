"""Interfaces owned by the application and implemented by external adapters.

``Protocol`` provides structural typing: an implementation does not need to inherit
from these classes; it only needs to supply methods with compatible signatures.
This keeps application services independent of OpenRouter, AWS and local test doubles.
"""

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from private_chat.domain.models import (
    Conversation,
    EncryptedPayload,
    ModelRequest,
    ModelResponse,
    StoredMessage,
)


class ModelProviderError(RuntimeError):
    """A model provider returned an unusable response or rejected the request."""


class ModelCatalog(Protocol):
    """Approved model metadata and validation, independent of a provider API."""

    def list_models(self) -> Sequence[object]:
        """Return browser-safe configured options."""

        ...

    def require_model(self, model_id: str) -> object:
        """Return an approved option or raise ``ValueError``."""

        ...


class ModelClient(Protocol):
    """Port shared by hosted and self-hosted inference adapters."""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate one normalised response from provider-neutral input."""

        ...


class ConversationRepository(Protocol):
    """Encrypted conversation persistence required by application use cases."""

    async def create_conversation(self, conversation: Conversation) -> None:
        """Create an empty conversation, rejecting an existing identifier."""

        ...

    async def list_conversations(self) -> Sequence[Conversation]:
        """Return conversation metadata newest first."""

        ...

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        """Return conversation metadata or ``None`` when it does not exist."""

        ...

    async def rename_conversation(self, conversation_id: UUID, title: str) -> None:
        """Persist a validated title or raise when the conversation does not exist."""

        ...

    async def list_messages(self, conversation_id: UUID) -> Sequence[StoredMessage]:
        """Return stored messages in their authoritative conversation order."""

        ...

    async def append_turn(
        self, conversation_id: UUID, user: StoredMessage, assistant: StoredMessage
    ) -> None:
        """Persist both sides of a completed turn atomically."""

        ...

    async def change_active_model(
        self, conversation_id: UUID, model_id: str, event: StoredMessage
    ) -> None:
        """Atomically persist the selection and encrypted timeline event."""

        ...

    async def delete_conversation(self, conversation_id: UUID) -> bool:
        """Delete a conversation and transcript, returning whether it existed."""

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


class ConversationInstructionsProvider(Protocol):
    """Supplies optional local instructions without exposing their storage."""

    def instructions(self) -> str | None:
        """Return non-empty instructions or ``None`` when not configured."""

        ...
