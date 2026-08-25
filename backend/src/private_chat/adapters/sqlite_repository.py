"""Durable local SQLite repository for application-encrypted conversations."""

import asyncio
import sqlite3
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from uuid import UUID

from private_chat.domain.models import Conversation, EncryptedPayload, Role, StoredMessage


class SqliteConversationRepository:
    """Store transcript ciphertext locally; plaintext never reaches SQLite."""

    _schema_version = 2

    def __init__(self, database_path: Path) -> None:
        self._path = database_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA secure_delete = ON")
        return connection

    def _initialise(self) -> None:
        connection = self._connect()
        try:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version not in (0, 1, self._schema_version):
                raise RuntimeError(f"Unsupported local conversation schema version {version}")
            connection.execute("PRAGMA journal_mode = WAL")
            if version == 0:
                connection.executescript(
                    """
                    BEGIN;
                    CREATE TABLE conversations (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        active_model_id TEXT
                    );
                    CREATE TABLE messages (
                        id TEXT PRIMARY KEY,
                        conversation_id TEXT NOT NULL REFERENCES conversations(id)
                            ON DELETE CASCADE,
                        position INTEGER NOT NULL,
                        role TEXT NOT NULL,
                        ciphertext BLOB NOT NULL,
                        nonce BLOB NOT NULL,
                        wrapped_data_key BLOB NOT NULL,
                        key_id TEXT NOT NULL,
                        algorithm TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(conversation_id, position)
                    );
                    CREATE INDEX messages_conversation_position
                        ON messages(conversation_id, position);
                    PRAGMA user_version = 2;
                    COMMIT;
                    """
                )
            elif version == 1:
                connection.executescript(
                    """
                    BEGIN;
                    ALTER TABLE conversations ADD COLUMN active_model_id TEXT;
                    PRAGMA user_version = 2;
                    COMMIT;
                    """
                )
        finally:
            connection.close()

    @staticmethod
    def _conversation(row: sqlite3.Row) -> Conversation:
        return Conversation(
            UUID(str(row["id"])),
            str(row["title"]),
            datetime.fromisoformat(str(row["created_at"])),
            None if row["active_model_id"] is None else str(row["active_model_id"]),
        )

    @staticmethod
    def _message(row: sqlite3.Row) -> StoredMessage:
        return StoredMessage(
            id=UUID(str(row["id"])),
            conversation_id=UUID(str(row["conversation_id"])),
            role=Role(str(row["role"])),
            encrypted_content=EncryptedPayload(
                ciphertext=bytes(row["ciphertext"]),
                nonce=bytes(row["nonce"]),
                wrapped_data_key=bytes(row["wrapped_data_key"]),
                key_id=str(row["key_id"]),
                algorithm=str(row["algorithm"]),
            ),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )

    async def create_conversation(self, conversation: Conversation) -> None:
        def create() -> None:
            connection = self._connect()
            try:
                connection.execute(
                    "INSERT INTO conversations(id, title, created_at, active_model_id) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        str(conversation.id),
                        conversation.title,
                        conversation.created_at.isoformat(),
                        conversation.active_model_id,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("Conversation already exists") from error
            finally:
                connection.close()

        await asyncio.to_thread(create)

    async def list_conversations(self) -> Sequence[Conversation]:
        def list_all() -> tuple[Conversation, ...]:
            connection = self._connect()
            try:
                rows = connection.execute(
                    "SELECT id, title, created_at, active_model_id FROM conversations "
                    "ORDER BY created_at DESC"
                ).fetchall()
                return tuple(self._conversation(row) for row in rows)
            finally:
                connection.close()

        return await asyncio.to_thread(list_all)

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        def get() -> Conversation | None:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT id, title, created_at, active_model_id FROM conversations WHERE id = ?",
                    (str(conversation_id),),
                ).fetchone()
                return None if row is None else self._conversation(row)
            finally:
                connection.close()

        return await asyncio.to_thread(get)

    async def list_messages(self, conversation_id: UUID) -> Sequence[StoredMessage]:
        def list_all() -> tuple[StoredMessage, ...]:
            connection = self._connect()
            try:
                rows = connection.execute(
                    "SELECT id, conversation_id, role, ciphertext, nonce, wrapped_data_key, "
                    "key_id, algorithm, created_at "
                    "FROM messages WHERE conversation_id = ? ORDER BY position ASC",
                    (str(conversation_id),),
                ).fetchall()
                return tuple(self._message(row) for row in rows)
            finally:
                connection.close()

        return await asyncio.to_thread(list_all)

    async def append_turn(
        self, conversation_id: UUID, user: StoredMessage, assistant: StoredMessage
    ) -> None:
        if user.conversation_id != conversation_id or assistant.conversation_id != conversation_id:
            raise ValueError("Stored messages do not belong to the target conversation")

        def append() -> None:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                exists = connection.execute(
                    "SELECT 1 FROM conversations WHERE id = ?", (str(conversation_id),)
                ).fetchone()
                if exists is None:
                    raise KeyError("Conversation does not exist")
                existing = {
                    str(row["id"])
                    for row in connection.execute(
                        "SELECT id FROM messages WHERE conversation_id = ? AND id IN (?, ?)",
                        (str(conversation_id), str(user.id), str(assistant.id)),
                    )
                }
                if existing == {str(user.id), str(assistant.id)}:
                    connection.execute("COMMIT")
                    return
                if existing:
                    raise RuntimeError("Conversation contains an incomplete duplicate turn")
                position = int(
                    connection.execute(
                        "SELECT COALESCE(MAX(position), -1) + 1 FROM messages "
                        "WHERE conversation_id = ?",
                        (str(conversation_id),),
                    ).fetchone()[0]
                )
                for offset, message in enumerate((user, assistant)):
                    payload = message.encrypted_content
                    connection.execute(
                        "INSERT INTO messages(id, conversation_id, position, role, "
                        "ciphertext, nonce, "
                        "wrapped_data_key, key_id, algorithm, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            str(message.id),
                            str(conversation_id),
                            position + offset,
                            message.role.value,
                            payload.ciphertext,
                            payload.nonce,
                            payload.wrapped_data_key,
                            payload.key_id,
                            payload.algorithm,
                            message.created_at.isoformat(),
                        ),
                    )
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            finally:
                connection.close()

        await asyncio.to_thread(append)

    async def change_active_model(
        self, conversation_id: UUID, model_id: str, event: StoredMessage
    ) -> None:
        if event.conversation_id != conversation_id:
            raise ValueError("Stored event does not belong to the target conversation")

        def change() -> None:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                if (
                    connection.execute(
                        "SELECT 1 FROM conversations WHERE id = ?", (str(conversation_id),)
                    ).fetchone()
                    is None
                ):
                    raise KeyError("Conversation does not exist")
                position = int(
                    connection.execute(
                        "SELECT COALESCE(MAX(position), -1) + 1 FROM messages "
                        "WHERE conversation_id = ?",
                        (str(conversation_id),),
                    ).fetchone()[0]
                )
                payload = event.encrypted_content
                connection.execute(
                    "UPDATE conversations SET active_model_id = ? WHERE id = ?",
                    (model_id, str(conversation_id)),
                )
                connection.execute(
                    "INSERT INTO messages(id, conversation_id, position, role, ciphertext, nonce, "
                    "wrapped_data_key, key_id, algorithm, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(event.id),
                        str(conversation_id),
                        position,
                        event.role.value,
                        payload.ciphertext,
                        payload.nonce,
                        payload.wrapped_data_key,
                        payload.key_id,
                        payload.algorithm,
                        event.created_at.isoformat(),
                    ),
                )
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            finally:
                connection.close()

        await asyncio.to_thread(change)

    async def delete_conversation(self, conversation_id: UUID) -> bool:
        def delete() -> bool:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                deleted = (
                    connection.execute(
                        "DELETE FROM conversations WHERE id = ?", (str(conversation_id),)
                    ).rowcount
                    > 0
                )
                connection.execute("COMMIT")
                if deleted:
                    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                return deleted
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            finally:
                connection.close()

        return await asyncio.to_thread(delete)
