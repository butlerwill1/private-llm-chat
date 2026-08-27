"""Durability and confidentiality checks for the local encrypted repository."""

import asyncio
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from private_chat.adapters.encryption import AesGcmEnvelopeEncryptor, LocalAesDataKeyProvider
from private_chat.adapters.sqlite_repository import SqliteConversationRepository
from private_chat.adapters.windows_dpapi import DpapiLocalDataKeyProvider
from private_chat.application.conversations import message_context
from private_chat.domain.models import Conversation, Role, StoredMessage


def repository_for(database: Path) -> SqliteConversationRepository:
    return SqliteConversationRepository(
        database, AesGcmEnvelopeEncryptor(LocalAesDataKeyProvider(b"t" * 32))
    )


def stored(conversation: Conversation, role: Role, body: str) -> StoredMessage:
    message_id = uuid4()
    encryptor = AesGcmEnvelopeEncryptor(LocalAesDataKeyProvider(b"k" * 32))
    return StoredMessage(
        id=message_id,
        conversation_id=conversation.id,
        role=role,
        encrypted_content=encryptor.encrypt(
            body.encode(), context=message_context(conversation.id, message_id)
        ),
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_sqlite_repository_persists_only_ciphertext_and_deletes_turns(tmp_path: Path) -> None:
    database = tmp_path / "conversations.sqlite3"
    repository = repository_for(database)
    conversation = Conversation.create()
    user = stored(conversation, Role.USER, "unique plaintext that must not reach sqlite")
    assistant = stored(conversation, Role.ASSISTANT, "unique encrypted answer")

    await repository.create_conversation(conversation)
    await repository.append_turn(conversation.id, user, assistant)
    await repository.rename_conversation(conversation.id, "Private reflections")
    restarted = repository_for(database)
    renamed = await restarted.get_conversation(conversation.id)
    assert renamed is not None
    assert renamed.title == "Private reflections"
    assert [item.id for item in await restarted.list_messages(conversation.id)] == [
        user.id,
        assistant.id,
    ]
    raw = database.read_bytes() + (
        database.with_name(database.name + "-wal").read_bytes()
        if database.with_name(database.name + "-wal").exists()
        else b""
    )
    assert b"unique plaintext that must not reach sqlite" not in raw
    assert b"Private reflections" not in raw
    assert await restarted.delete_conversation(conversation.id)
    assert await restarted.get_conversation(conversation.id) is None


@pytest.mark.asyncio
async def test_sqlite_repository_keeps_turn_writes_atomic(tmp_path: Path) -> None:
    repository = repository_for(tmp_path / "conversations.sqlite3")
    conversation = Conversation.create()
    await repository.create_conversation(conversation)
    user = stored(conversation, Role.USER, "one")
    assistant = stored(conversation, Role.ASSISTANT, "two")
    await asyncio.gather(
        repository.append_turn(conversation.id, user, assistant),
        repository.append_turn(conversation.id, user, assistant),
    )
    assert [item.id for item in await repository.list_messages(conversation.id)] == [
        user.id,
        assistant.id,
    ]


@pytest.mark.asyncio
async def test_sqlite_repository_migrates_legacy_plaintext_titles(tmp_path: Path) -> None:
    database = tmp_path / "conversations.sqlite3"
    conversation = Conversation.create("Legacy private title")
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            active_model_id TEXT
        );
        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            role TEXT NOT NULL,
            ciphertext BLOB NOT NULL,
            nonce BLOB NOT NULL,
            wrapped_data_key BLOB NOT NULL,
            key_id TEXT NOT NULL,
            algorithm TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        PRAGMA user_version = 2;
        """
    )
    connection.execute(
        "INSERT INTO conversations(id, title, created_at, active_model_id) VALUES (?, ?, ?, ?)",
        (str(conversation.id), conversation.title, conversation.created_at.isoformat(), None),
    )
    connection.commit()
    connection.close()

    repository = repository_for(database)
    migrated = await repository.get_conversation(conversation.id)
    assert migrated is not None
    assert migrated.title == "Legacy private title"
    assert b"Legacy private title" not in database.read_bytes()


@pytest.mark.skipif(os.name != "nt", reason="DPAPI is a Windows current-user service")
def test_dpapi_key_survives_restart_but_missing_key_fails_closed(tmp_path: Path) -> None:
    database = tmp_path / "conversations.sqlite3"
    database.write_bytes(b"SQLite format placeholder")
    # The first run uses an empty database placeholder only to establish the key file.
    key_path = tmp_path / "master-key.dpapi"
    database.unlink()
    first = DpapiLocalDataKeyProvider.load_or_create(tmp_path, database_path=database)
    second = DpapiLocalDataKeyProvider.load_or_create(tmp_path, database_path=database)
    assert first.key_id == second.key_id
    database.write_bytes(b"existing encrypted database")
    key_path.unlink()
    with pytest.raises(RuntimeError, match="key is missing"):
        DpapiLocalDataKeyProvider.load_or_create(tmp_path, database_path=database)
