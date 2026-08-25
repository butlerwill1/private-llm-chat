"""Conversation lifecycle use cases independent of HTTP and persistence vendors."""

import asyncio
from dataclasses import dataclass
from uuid import UUID

from private_chat.application.message_payload import decode_message_payload, encode_message_payload
from private_chat.application.model_router import ConfiguredModelCatalog
from private_chat.domain.models import ChatMessage, Conversation, Role, StoredMessage
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
        self,
        repository: ConversationRepository,
        encryptor: EnvelopeEncryptor,
        catalog: ConfiguredModelCatalog,
        default_model_id: str,
    ) -> None:
        self._repository = repository
        self._encryptor = encryptor
        self._catalog = catalog
        self._default_model_id = default_model_id

    async def create(self, model_id: str | None = None) -> ConversationView:
        selected_model = model_id or self._default_model_id
        self._catalog.require_model(selected_model)
        conversation = Conversation.create(active_model_id=selected_model)
        await self._repository.create_conversation(conversation)
        return ConversationView(conversation, ())

    async def change_model(self, conversation_id: UUID, model_id: str) -> ConversationView:
        new_model = self._catalog.require_model(model_id)
        current = await self._repository.get_conversation(conversation_id)
        if current is None:
            raise KeyError("Conversation does not exist")
        old_model = current.active_model_id or self._default_model_id
        self._catalog.require_model(old_model)
        if old_model != model_id:
            old_label = self._catalog.require_model(old_model).label
            event = ChatMessage.create(
                Role.SYSTEM,
                f"Model changed from {old_label} to {new_model.label}.",
            )
            stored = StoredMessage(
                id=event.id,
                conversation_id=conversation_id,
                role=event.role,
                encrypted_content=await asyncio.to_thread(
                    self._encryptor.encrypt,
                    encode_message_payload(event.content, None),
                    context=message_context(conversation_id, event.id),
                ),
                created_at=event.created_at,
            )
            await self._repository.change_active_model(conversation_id, model_id, stored)
        view = await self.get(conversation_id)
        if view is None:
            raise KeyError("Conversation does not exist")
        return view

    async def get(self, conversation_id: UUID) -> ConversationView | None:
        conversation = await self._repository.get_conversation(conversation_id)
        if conversation is None:
            return None
        records = await self._repository.list_messages(conversation_id)

        async def decrypt(record: StoredMessage) -> ChatMessage:
            plaintext = await asyncio.to_thread(
                self._encryptor.decrypt,
                record.encrypted_content,
                context=message_context(conversation_id, record.id),
            )
            payload = decode_message_payload(plaintext)
            return ChatMessage(
                role=record.role,
                content=payload.content,
                id=record.id,
                created_at=record.created_at,
                usage=payload.usage,
            )

        # KMS is a synchronous SDK boundary, so run each decrypt outside the
        # FastAPI event loop. Sequential calls avoid bursting a personal KMS quota.
        messages = tuple([await decrypt(record) for record in records])
        inferred_model = next(
            (
                message.usage.model
                for message in reversed(messages)
                if message.role is Role.ASSISTANT and message.usage is not None
            ),
            None,
        )
        if conversation.active_model_id is None and inferred_model is not None:
            conversation = Conversation(
                id=conversation.id,
                title=conversation.title,
                created_at=conversation.created_at,
                active_model_id=inferred_model,
            )
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
