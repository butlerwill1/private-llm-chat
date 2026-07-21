"""Application-layer tests for the send-message business workflow."""

from uuid import uuid4

import pytest

from private_chat.adapters.encryption import AesGcmEnvelopeEncryptor, LocalAesDataKeyProvider
from private_chat.adapters.memory_repository import InMemoryConversationRepository
from private_chat.application.send_message import SendMessage, SendMessageCommand
from private_chat.domain.models import Conversation, ModelRequest, ModelResponse, Role


class RecordingModelClient:
    """Model double that records prompts so tests can inspect reconstructed history."""

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Record the exact model request and return a deterministic response."""

        self.requests.append(request)
        return ModelResponse("A private answer", request.model, "test")


@pytest.mark.asyncio
async def test_turn_is_stored_encrypted_and_history_is_rehydrated() -> None:
    """Each turn is encrypted at rest while later prompts receive plaintext history.

    Two turns are needed to prove both sides of the boundary: the repository
    retains encrypted records, but the use case decrypts earlier messages before
    constructing the next model request in chronological order.
    """

    repository = InMemoryConversationRepository()
    model = RecordingModelClient()
    use_case = SendMessage(
        repository,
        AesGcmEnvelopeEncryptor(LocalAesDataKeyProvider(b"x" * 32)),
        model,
        "m1",
    )
    conversation = Conversation.create()
    await repository.create_conversation(conversation)
    conversation_id = conversation.id

    first = await use_case.execute(SendMessageCommand(conversation_id, "Sensitive text"))
    second = await use_case.execute(SendMessageCommand(conversation_id, "Follow up"))

    stored = await repository.list_messages(conversation_id)
    # A turn is persisted atomically as one user and one assistant record.
    assert first.role is Role.ASSISTANT
    assert second.content == "A private answer"
    assert len(stored) == 4
    # Plaintext must not appear directly in the repository's ciphertext field.
    assert b"Sensitive text" not in stored[0].encrypted_content.ciphertext
    # The second prompt must nevertheless contain the decrypted first turn plus
    # the new user message, which is the context expected by a chat model.
    assert [message.content for message in model.requests[1].messages] == [
        "Sensitive text",
        "A private answer",
        "Follow up",
    ]


@pytest.mark.asyncio
async def test_blank_message_is_rejected_before_model_call() -> None:
    """Whitespace-only input should fail before inference or persistence occurs.

    This protects model capacity and ensures invalid domain input cannot cause an
    external side effect before validation reports the problem.
    """

    model = RecordingModelClient()
    repository = InMemoryConversationRepository()
    conversation = Conversation.create()
    await repository.create_conversation(conversation)
    use_case = SendMessage(
        repository,
        AesGcmEnvelopeEncryptor(LocalAesDataKeyProvider(b"x" * 32)),
        model,
        "m1",
    )
    with pytest.raises(ValueError, match="blank"):
        await use_case.execute(SendMessageCommand(conversation.id, "   "))
    assert model.requests == []  # No inference call escaped validation.


@pytest.mark.asyncio
async def test_unknown_conversation_is_rejected_before_model_call() -> None:
    """Messages cannot create implicit transcripts for unknown conversation IDs.

    Requiring an existing aggregate prevents orphan records and ensures callers
    follow the explicit conversation-creation lifecycle.
    """

    model = RecordingModelClient()
    use_case = SendMessage(
        InMemoryConversationRepository(),
        AesGcmEnvelopeEncryptor(LocalAesDataKeyProvider(b"x" * 32)),
        model,
        "m1",
    )
    with pytest.raises(KeyError, match="does not exist"):
        await use_case.execute(SendMessageCommand(uuid4(), "Hello"))
    assert model.requests == []  # Missing state is detected before inference.
