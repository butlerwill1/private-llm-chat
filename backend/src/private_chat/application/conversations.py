"""Conversation lifecycle use cases independent of HTTP and persistence vendors."""

import asyncio
from dataclasses import dataclass
from uuid import UUID

from private_chat.domain.models import ChatMessage, Conversation, StoredMessage
from private_chat.ports.interfaces import ConversationRepository, EnvelopeEncryptor


def message_context(conversation_id: UUID, message_id: UUID) -> bytes:
    """Build authenticated context that prevents ciphertext record swapping."""

    return f"conversation={conversation_id};message={message_id}".encode()


@dataclass(frozen=True, slots=True)
class ConversationView:
    """Decrypted application view returned only to an authorised local caller."""

    conversation: Conversation
    messages: tuple[ChatMessage, ...]


class ConversationService:
    """Create, read and delete conversations through the repository port."""

    def __init__(
        self, repository: ConversationRepository, encryptor: EnvelopeEncryptor
    ) -> None:
        self._repository = repository
        self._encryptor = encryptor

    async def create(self) -> ConversationView:
        conversation = Conversation.create()
        await self._repository.create_conversation(conversation)
        return ConversationView(conversation, ())

    async def get(self, conversation_id: UUID) -> ConversationView | None:
        conversation = await self._repository.get_conversation(conversation_id)
        if conversation is None:
            return None
        records = await self._repository.list_messages(conversation_id)
        async def decrypt(record: StoredMessage) -> ChatMessage:
            content = await asyncio.to_thread(
                self._encryptor.decrypt,
                record.encrypted_content,
                context=message_context(conversation_id, record.id),
            )
            return ChatMessage(
                role=record.role,
                content=content.decode(),
                id=record.id,
                created_at=record.created_at,
            )

        # KMS is a synchronous SDK boundary, so run each decrypt outside the
        # FastAPI event loop. Sequential calls avoid bursting a personal KMS quota.
        messages = tuple([await decrypt(record) for record in records])
        return ConversationView(conversation, messages)

    async def list(self) -> tuple[ConversationView, ...]:
        conversations = await self._repository.list_conversations()
        # Reads are independent. Keeping the implementation sequential avoids a
        # burst of KMS decrypt requests for a large personal transcript archive.
        views: list[ConversationView] = []
        for conversation in conversations:
            view = await self.get(conversation.id)
            if view is not None:
                views.append(view)
        return tuple(views)

    async def list_metadata(self) -> tuple[Conversation, ...]:
        """Return sidebar-safe metadata without decrypting every transcript.

        Loading a sidebar must not make one KMS decrypt request per historical
        message. Callers fetch the selected conversation separately when its
        transcript is actually needed.
        """

        return tuple(await self._repository.list_conversations())

    async def delete(self, conversation_id: UUID) -> bool:
        return await self._repository.delete_conversation(conversation_id)
