import asyncio
from dataclasses import dataclass
from uuid import UUID

from private_chat.application.conversations import message_context
from private_chat.application.message_payload import decode_message_payload, encode_message_payload
from private_chat.domain.models import ChatMessage, ModelRequest, Role, StoredMessage, TurnUsage
from private_chat.ports.interfaces import ConversationRepository, EnvelopeEncryptor, ModelClient


@dataclass(frozen=True, slots=True)
class SendMessageCommand:
    conversation_id: UUID
    content: str
    model_id: str | None = None


class SendMessage:
    """Orchestrates one turn without coupling business logic to FastAPI or a vendor."""

    def __init__(
        self,
        repository: ConversationRepository,
        encryptor: EnvelopeEncryptor,
        model_client: ModelClient,
        model_name: str,
    ) -> None:
        self._repository = repository
        self._encryptor = encryptor
        self._model_client = model_client
        self._model_name = model_name

    async def execute(self, command: SendMessageCommand) -> ChatMessage:
        if await self._repository.get_conversation(command.conversation_id) is None:
            raise KeyError("Conversation does not exist")
        user = ChatMessage.create(Role.USER, command.content)
        history_records = await self._repository.list_messages(command.conversation_id)
        history = tuple(
            ChatMessage(
                role=item.role,
                content=decode_message_payload(
                    self._encryptor.decrypt(
                        item.encrypted_content,
                        context=message_context(command.conversation_id, item.id),
                    )
                ).content,
                id=item.id,
                created_at=item.created_at,
            )
            for item in history_records
        )
        response = await self._model_client.generate(
            ModelRequest(messages=(*history, user), model=command.model_id or self._model_name)
        )
        usage = response.usage or TurnUsage.unavailable(
            model=response.model, provider=response.provider
        )
        user = ChatMessage(user.role, user.content, user.id, user.created_at, usage)
        assistant_message = ChatMessage.create(Role.ASSISTANT, response.content)
        assistant = ChatMessage(
            assistant_message.role,
            assistant_message.content,
            assistant_message.id,
            assistant_message.created_at,
            usage,
        )

        async def stored(message: ChatMessage) -> StoredMessage:
            return StoredMessage(
                id=message.id,
                conversation_id=command.conversation_id,
                role=message.role,
                encrypted_content=await asyncio.to_thread(
                    self._encryptor.encrypt,
                    encode_message_payload(message.content, message.usage),
                    context=message_context(command.conversation_id, message.id),
                ),
                created_at=message.created_at,
            )

        # The repository owns atomicity: a failed write must not leave a one-sided turn.
        await self._repository.append_turn(
            command.conversation_id, await stored(user), await stored(assistant)
        )
        return assistant
