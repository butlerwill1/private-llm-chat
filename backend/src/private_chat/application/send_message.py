from dataclasses import dataclass
from uuid import UUID

from private_chat.domain.models import ChatMessage, ModelRequest, Role, StoredMessage
from private_chat.ports.interfaces import ConversationRepository, EnvelopeEncryptor, ModelClient


@dataclass(frozen=True, slots=True)
class SendMessageCommand:
    conversation_id: UUID
    content: str
    model: str


class SendMessage:
    """Orchestrates one turn without coupling business logic to FastAPI or a vendor."""

    def __init__(
        self,
        repository: ConversationRepository,
        encryptor: EnvelopeEncryptor,
        model_client: ModelClient,
    ) -> None:
        self._repository = repository
        self._encryptor = encryptor
        self._model_client = model_client

    @staticmethod
    def _context(conversation_id: UUID, message_id: UUID) -> bytes:
        # Binding ciphertext to both identifiers prevents it being copied into another
        # conversation or record and successfully decrypted there.
        return f"conversation={conversation_id};message={message_id}".encode()

    async def execute(self, command: SendMessageCommand) -> ChatMessage:
        user = ChatMessage.create(Role.USER, command.content)
        history_records = await self._repository.list_messages(command.conversation_id)
        history = tuple(
            ChatMessage(
                role=item.role,
                content=self._encryptor.decrypt(
                    item.encrypted_content,
                    context=self._context(command.conversation_id, item.id),
                ).decode(),
                id=item.id,
                created_at=item.created_at,
            )
            for item in history_records
        )
        response = await self._model_client.generate(
            ModelRequest(messages=(*history, user), model=command.model)
        )
        assistant = ChatMessage.create(Role.ASSISTANT, response.content)

        def stored(message: ChatMessage) -> StoredMessage:
            return StoredMessage(
                id=message.id,
                conversation_id=command.conversation_id,
                role=message.role,
                encrypted_content=self._encryptor.encrypt(
                    message.content.encode(),
                    context=self._context(command.conversation_id, message.id),
                ),
                created_at=message.created_at,
            )

        # The repository owns atomicity: a failed write must not leave a one-sided turn.
        await self._repository.append_turn(
            command.conversation_id, stored(user), stored(assistant)
        )
        return assistant
