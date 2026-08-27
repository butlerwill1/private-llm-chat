import asyncio
from collections.abc import Sequence
from uuid import UUID

from private_chat.domain.models import (
    Conversation,
    EncryptedPayload,
    StoredMessage,
    conversation_title_context,
)
from private_chat.ports.interfaces import EnvelopeEncryptor


class InMemoryConversationRepository:
    """Process-local repository intended for tests and local demonstrations only."""

    def __init__(self, encryptor: EnvelopeEncryptor) -> None:
        self._encryptor = encryptor
        self._conversations: dict[UUID, Conversation] = {}
        self._titles: dict[UUID, EncryptedPayload] = {}
        self._messages: dict[UUID, list[StoredMessage]] = {}
        self._lock = asyncio.Lock()

    async def create_conversation(self, conversation: Conversation) -> None:
        async with self._lock:
            if conversation.id in self._conversations:
                raise ValueError("Conversation already exists")
            self._conversations[conversation.id] = Conversation(
                id=conversation.id,
                title="",
                created_at=conversation.created_at,
                active_model_id=conversation.active_model_id,
            )
            self._titles[conversation.id] = self._encryptor.encrypt(
                conversation.title.encode(), context=conversation_title_context(conversation.id)
            )
            self._messages[conversation.id] = []

    async def list_conversations(self) -> Sequence[Conversation]:
        async with self._lock:
            return tuple(
                self._with_title(conversation)
                for conversation in sorted(
                    self._conversations.values(), key=lambda item: item.created_at, reverse=True
                )
            )

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        async with self._lock:
            conversation = self._conversations.get(conversation_id)
            return None if conversation is None else self._with_title(conversation)

    async def rename_conversation(self, conversation_id: UUID, title: str) -> None:
        async with self._lock:
            conversation = self._conversations.get(conversation_id)
            if conversation is None:
                raise KeyError("Conversation does not exist")
            self._titles[conversation_id] = self._encryptor.encrypt(
                conversation.renamed(title).title.encode(),
                context=conversation_title_context(conversation_id),
            )

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
            self._titles.pop(conversation_id, None)
            self._messages.pop(conversation_id, None)
            return True

    def _with_title(self, conversation: Conversation) -> Conversation:
        title = self._encryptor.decrypt(
            self._titles[conversation.id], context=conversation_title_context(conversation.id)
        ).decode()
        return Conversation(
            id=conversation.id,
            title=title,
            created_at=conversation.created_at,
            active_model_id=conversation.active_model_id,
        )
