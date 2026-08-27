"""Application-layer tests for the send-message business workflow."""

from decimal import Decimal
from uuid import uuid4

import pytest

from private_chat.adapters.encryption import AesGcmEnvelopeEncryptor, LocalAesDataKeyProvider
from private_chat.adapters.memory_repository import InMemoryConversationRepository
from private_chat.application.conversations import message_context
from private_chat.application.message_payload import decode_message_payload
from private_chat.application.send_message import SendMessage, SendMessageCommand
from private_chat.domain.models import (
    Conversation,
    CostBasis,
    ModelRequest,
    ModelResponse,
    Role,
    TurnUsage,
)


class RecordingModelClient:
    """Model double that records prompts so tests can inspect reconstructed history."""

    def __init__(self) -> None:
        # Every received request is appended here for assertions after execution.
        self.requests: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Record the exact model request and return a deterministic response."""

        self.requests.append(request)
        # Echo request.model into the response to behave like a normal adapter.
        return ModelResponse(
            "A private answer",
            request.model,
            "test",
            TurnUsage(
                20, 5, 25, 0, 0, 0, Decimal("0.000123"), CostBasis.PROVIDER_REPORTED,
                request.model, "test",
            ),
        )


def make_repository() -> InMemoryConversationRepository:
    return InMemoryConversationRepository(
        AesGcmEnvelopeEncryptor(LocalAesDataKeyProvider(b"r" * 32))
    )


@pytest.mark.asyncio
async def test_turn_is_stored_encrypted_and_history_is_rehydrated() -> None:
    """Each turn is encrypted at rest while later prompts receive plaintext history.

    Two turns are needed to prove both sides of the boundary: the repository
    retains encrypted records, but the use case decrypts earlier messages before
    constructing the next model request in chronological order.
    """

    # Arrange the three dependencies required by SendMessage: persistence,
    # encryption and inference. All are local and deterministic in this test.
    repository = make_repository()
    model = RecordingModelClient()
    encryptor = AesGcmEnvelopeEncryptor(LocalAesDataKeyProvider(b"x" * 32))
    use_case = SendMessage(repository, encryptor, model, "m1")
    # Conversation.create generates the UUID and timestamp domain values.
    conversation = Conversation.create()
    # Store it explicitly because SendMessage rejects unknown conversation IDs.
    await repository.create_conversation(conversation)
    conversation_id = conversation.id

    # Act twice. The second call is what forces the use case to read, decrypt and
    # include the first turn when constructing the next model request.
    first = await use_case.execute(SendMessageCommand(conversation_id, "Sensitive text"))
    second = await use_case.execute(SendMessageCommand(conversation_id, "Follow up"))

    # Read the repository's storage-facing records rather than an API view so the
    # test can inspect whether their content is encrypted.
    stored = await repository.list_messages(conversation_id)
    # A turn is persisted atomically as one user and one assistant record.
    assert first.role is Role.ASSISTANT
    assert second.content == "A private answer"
    assert len(stored) == 4
    # Plaintext must not appear directly in the repository's ciphertext field.
    assert b"Sensitive text" not in stored[0].encrypted_content.ciphertext
    assert b"0.000123" not in stored[0].encrypted_content.ciphertext
    # The second prompt must nevertheless contain the decrypted first turn plus
    # the new user message, which is the context expected by a chat model.
    assert [message.content for message in model.requests[1].messages] == [
        "Sensitive text",
        "A private answer",
        "Follow up",
    ]
    first_payload = decode_message_payload(
        encryptor.decrypt(
            stored[0].encrypted_content,
            context=message_context(conversation_id, stored[0].id),
        )
    )
    second_payload = decode_message_payload(
        encryptor.decrypt(
            stored[1].encrypted_content,
            context=message_context(conversation_id, stored[1].id),
        )
    )
    assert first_payload.usage == second_payload.usage
    assert first_payload.usage is not None
    assert first_payload.usage.cost_usd == Decimal("0.000123")


@pytest.mark.asyncio
async def test_blank_message_is_rejected_before_model_call() -> None:
    """Whitespace-only input should fail before inference or persistence occurs.

    This protects model capacity and ensures invalid domain input cannot cause an
    external side effect before validation reports the problem.
    """

    # Arrange a valid existing conversation so blank content is the only invalid
    # part of the command and therefore the certain cause of the exception.
    model = RecordingModelClient()
    repository = make_repository()
    conversation = Conversation.create()
    await repository.create_conversation(conversation)
    use_case = SendMessage(
        repository,
        AesGcmEnvelopeEncryptor(LocalAesDataKeyProvider(b"x" * 32)),
        model,
        "m1",
    )
    # Act and Assert: pytest.raises passes only if this block raises ValueError.
    # `match` additionally checks the message so an unrelated ValueError cannot pass.
    with pytest.raises(ValueError, match="blank"):
        await use_case.execute(SendMessageCommand(conversation.id, "   "))
    assert model.requests == []  # No inference call escaped validation.


@pytest.mark.asyncio
async def test_unknown_conversation_is_rejected_before_model_call() -> None:
    """Messages cannot create implicit transcripts for unknown conversation IDs.

    Requiring an existing aggregate prevents orphan records and ensures callers
    follow the explicit conversation-creation lifecycle.
    """

    # Arrange an empty repository: unlike the previous test, no conversation is
    # inserted before executing the command.
    model = RecordingModelClient()
    use_case = SendMessage(
        make_repository(),
        AesGcmEnvelopeEncryptor(LocalAesDataKeyProvider(b"x" * 32)),
        model,
        "m1",
    )
    # uuid4 creates a syntactically valid but unknown identifier, isolating the
    # test from UUID parsing and focusing it on aggregate existence.
    with pytest.raises(KeyError, match="does not exist"):
        await use_case.execute(SendMessageCommand(uuid4(), "Hello"))
    assert model.requests == []  # Missing state is detected before inference.
