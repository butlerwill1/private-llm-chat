from uuid import uuid4

import pytest

from private_chat.adapters.encryption import AesGcmEnvelopeEncryptor, LocalAesDataKeyProvider
from private_chat.adapters.memory_repository import InMemoryConversationRepository
from private_chat.application.send_message import SendMessage, SendMessageCommand
from private_chat.domain.models import ModelRequest, ModelResponse, Role


class RecordingModelClient:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse("A private answer", request.model, "test")


@pytest.mark.asyncio
async def test_turn_is_stored_encrypted_and_history_is_rehydrated() -> None:
    repository = InMemoryConversationRepository()
    model = RecordingModelClient()
    use_case = SendMessage(
        repository,
        AesGcmEnvelopeEncryptor(LocalAesDataKeyProvider(b"x" * 32)),
        model,
    )
    conversation_id = uuid4()

    first = await use_case.execute(SendMessageCommand(conversation_id, "Sensitive text", "m1"))
    second = await use_case.execute(SendMessageCommand(conversation_id, "Follow up", "m1"))

    stored = await repository.list_messages(conversation_id)
    assert first.role is Role.ASSISTANT
    assert second.content == "A private answer"
    assert len(stored) == 4
    assert b"Sensitive text" not in stored[0].encrypted_content.ciphertext
    assert [message.content for message in model.requests[1].messages] == [
        "Sensitive text",
        "A private answer",
        "Follow up",
    ]


@pytest.mark.asyncio
async def test_blank_message_is_rejected_before_model_call() -> None:
    model = RecordingModelClient()
    use_case = SendMessage(
        InMemoryConversationRepository(),
        AesGcmEnvelopeEncryptor(LocalAesDataKeyProvider(b"x" * 32)),
        model,
    )
    with pytest.raises(ValueError, match="blank"):
        await use_case.execute(SendMessageCommand(uuid4(), "   ", "m1"))
    assert model.requests == []

