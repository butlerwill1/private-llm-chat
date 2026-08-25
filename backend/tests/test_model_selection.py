"""Application tests for durable model selection and local instructions."""

from pathlib import Path

import pytest

from private_chat.adapters.conversation_instructions import FileConversationInstructionsProvider
from private_chat.adapters.encryption import AesGcmEnvelopeEncryptor, LocalAesDataKeyProvider
from private_chat.adapters.memory_repository import InMemoryConversationRepository
from private_chat.application.conversations import ConversationService
from private_chat.application.model_router import ConfiguredModelCatalog, ModelOption
from private_chat.application.send_message import SendMessage, SendMessageCommand
from private_chat.domain.models import ModelRequest, ModelResponse, Role


class RecordingModel:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse("answer", request.model, "test-provider")


def catalog() -> ConfiguredModelCatalog:
    return ConfiguredModelCatalog(
        (
            ModelOption("model-a", "Model A", "test"),
            ModelOption("model-b", "Model B", "test"),
        )
    )


@pytest.mark.asyncio
async def test_switching_model_persists_an_encrypted_event_and_uses_new_model(
    tmp_path: Path,
) -> None:
    repository = InMemoryConversationRepository()
    encryptor = AesGcmEnvelopeEncryptor(LocalAesDataKeyProvider(b"x" * 32))
    service = ConversationService(repository, encryptor, catalog(), "model-a")
    created = await service.create()

    changed = await service.change_model(created.conversation.id, "model-b")
    assert changed.conversation.active_model_id == "model-b"
    assert [(message.role, message.content) for message in changed.messages] == [
        (Role.SYSTEM, "Model changed from Model A to Model B."),
    ]
    raw = await repository.list_messages(created.conversation.id)
    assert b"Model changed" not in raw[0].encrypted_content.ciphertext

    instructions = tmp_path / "conversation-instructions.md"
    instructions.write_text("Reflect carefully.", encoding="utf-8")
    model = RecordingModel()
    send = SendMessage(
        repository,
        encryptor,
        model,
        "model-a",
        FileConversationInstructionsProvider(instructions),
    )
    await send.execute(SendMessageCommand(created.conversation.id, "hello"))
    request = model.requests[0]
    assert request.model == "model-b"
    assert [(message.role, message.content) for message in request.messages] == [
        (Role.SYSTEM, "Reflect carefully."),
        (Role.USER, "hello"),
    ]


def test_missing_instructions_file_is_safely_omitted(tmp_path: Path) -> None:
    assert FileConversationInstructionsProvider(tmp_path / "missing.md").instructions() is None
