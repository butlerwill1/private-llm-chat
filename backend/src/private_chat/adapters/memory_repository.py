import asyncio
from collections.abc import Sequence
from uuid import UUID

from private_chat.domain.models import StoredMessage


class InMemoryConversationRepository:
    """Process-local repository intended for tests and local demonstrations only."""

    def __init__(self) -> None:
        self._messages: dict[UUID, list[StoredMessage]] = {}
        self._lock = asyncio.Lock()

    async def list_messages(self, conversation_id: UUID) -> Sequence[StoredMessage]:
        async with self._lock:
            return tuple(self._messages.get(conversation_id, ()))

    async def append_turn(
        self, conversation_id: UUID, user: StoredMessage, assistant: StoredMessage
    ) -> None:
        if user.conversation_id != conversation_id or assistant.conversation_id != conversation_id:
            raise ValueError("Stored messages do not belong to the target conversation")
        async with self._lock:
            self._messages.setdefault(conversation_id, []).extend((user, assistant))

