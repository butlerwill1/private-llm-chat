import asyncio
from collections.abc import Sequence
from uuid import UUID

from private_chat.domain.models import Conversation, StoredMessage


class InMemoryConversationRepository:
    """Process-local repository intended for tests and local demonstrations only."""

    def __init__(self) -> None:
        self._conversations: dict[UUID, Conversation] = {}
        self._messages: dict[UUID, list[StoredMessage]] = {}
        self._lock = asyncio.Lock()

    async def create_conversation(self, conversation: Conversation) -> None:
        async with self._lock:
            if conversation.id in self._conversations:
                raise ValueError("Conversation already exists")
            self._conversations[conversation.id] = conversation
            self._messages[conversation.id] = []

    async def list_conversations(self) -> Sequence[Conversation]:
        async with self._lock:
            return tuple(
                sorted(self._conversations.values(), key=lambda item: item.created_at, reverse=True)
            )

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        async with self._lock:
            return self._conversations.get(conversation_id)

    async def list_messages(self, conversation_id: UUID) -> Sequence[StoredMessage]:
        async with self._lock:
            return tuple(self._messages.get(conversation_id, ()))

    async def append_turn(
        self, conversation_id: UUID, user: StoredMessage, assistant: StoredMessage
    ) -> None:
        if user.conversation_id != conversation_id or assistant.conversation_id != conversation_id:
            raise ValueError("Stored messages do not belong to the target conversation")
        async with self._lock:
            if conversation_id not in self._conversations:
                raise KeyError("Conversation does not exist")
            self._messages[conversation_id].extend((user, assistant))

    async def change_active_model(
        self, conversation_id: UUID, model_id: str, event: StoredMessage
    ) -> None:
        if event.conversation_id != conversation_id:
            raise ValueError("Stored event does not belong to the target conversation")
        async with self._lock:
            conversation = self._conversations.get(conversation_id)
            if conversation is None:
                raise KeyError("Conversation does not exist")
            self._conversations[conversation_id] = Conversation(
                id=conversation.id,
                title=conversation.title,
                created_at=conversation.created_at,
                active_model_id=model_id,
            )
            self._messages[conversation_id].append(event)

    async def delete_conversation(self, conversation_id: UUID) -> bool:
        async with self._lock:
            if self._conversations.pop(conversation_id, None) is None:
                return False
            self._messages.pop(conversation_id, None)
            return True
