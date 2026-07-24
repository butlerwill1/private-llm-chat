"""Durable, encrypted S3 implementation of the conversation repository port."""

import asyncio
import base64
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from botocore.exceptions import ClientError
from pydantic import BaseModel, ConfigDict

from private_chat.domain.models import Conversation, EncryptedPayload, Role, StoredMessage


class EncryptedPayloadRecord(BaseModel):
    """Strict JSON representation of binary encrypted payload fields."""

    model_config = ConfigDict(extra="forbid")
    ciphertext_b64: str
    nonce_b64: str
    wrapped_data_key_b64: str
    key_id: str
    algorithm: str

    @staticmethod
    def _encode(value: bytes) -> str:
        return base64.b64encode(value).decode("ascii")

    @staticmethod
    def _decode(value: str) -> bytes:
        return base64.b64decode(value, validate=True)

    @classmethod
    def from_domain(cls, payload: EncryptedPayload) -> "EncryptedPayloadRecord":
        return cls(
            ciphertext_b64=cls._encode(payload.ciphertext),
            nonce_b64=cls._encode(payload.nonce),
            wrapped_data_key_b64=cls._encode(payload.wrapped_data_key),
            key_id=payload.key_id,
            algorithm=payload.algorithm,
        )

    def to_domain(self) -> EncryptedPayload:
        return EncryptedPayload(
            ciphertext=self._decode(self.ciphertext_b64),
            nonce=self._decode(self.nonce_b64),
            wrapped_data_key=self._decode(self.wrapped_data_key_b64),
            key_id=self.key_id,
            algorithm=self.algorithm,
        )


class StoredMessageRecord(BaseModel):
    """Strict persisted message schema used to detect corrupt S3 documents."""

    model_config = ConfigDict(extra="forbid")
    id: UUID
    conversation_id: UUID
    role: Role
    encrypted_content: EncryptedPayloadRecord
    created_at: datetime

    @classmethod
    def from_domain(cls, message: StoredMessage) -> "StoredMessageRecord":
        return cls(
            id=message.id,
            conversation_id=message.conversation_id,
            role=message.role,
            encrypted_content=EncryptedPayloadRecord.from_domain(message.encrypted_content),
            created_at=message.created_at,
        )

    def to_domain(self) -> StoredMessage:
        return StoredMessage(
            id=self.id,
            conversation_id=self.conversation_id,
            role=self.role,
            encrypted_content=self.encrypted_content.to_domain(),
            created_at=self.created_at,
        )


class ConversationDocument(BaseModel):
    """One versioned S3 object containing metadata and an authoritative transcript."""

    model_config = ConfigDict(extra="forbid")
    schema_version: int = 1
    id: UUID
    title: str
    created_at: datetime
    messages: list[StoredMessageRecord]

    def conversation(self) -> Conversation:
        return Conversation(id=self.id, title=self.title, created_at=self.created_at)


class S3ConversationRepository:
    """Store one conditionally-updated, SSE-KMS object per conversation.

    Message bodies are already envelope-encrypted by the application. SSE-KMS is
    an additional storage control, not a substitute for that application layer.
    """

    _prefix = "conversations/"

    def __init__(self, client: Any, bucket: str, kms_key_id: str) -> None:
        self._client = client
        self._bucket = bucket
        self._kms_key_id = kms_key_id

    @classmethod
    def _key(cls, conversation_id: UUID) -> str:
        return f"{cls._prefix}{conversation_id}.json"

    @staticmethod
    def _is_missing(error: ClientError) -> bool:
        return str(error.response.get("Error", {}).get("Code")) in {"404", "NoSuchKey"}

    def _put(self, key: str, document: ConversationDocument, **conditions: str) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=document.model_dump_json().encode(),
            ContentType="application/json",
            ServerSideEncryption="aws:kms",
            SSEKMSKeyId=self._kms_key_id,
            **conditions,
        )

    def _get(self, conversation_id: UUID) -> tuple[ConversationDocument, str] | None:
        try:
            response = self._client.get_object(
                Bucket=self._bucket, Key=self._key(conversation_id)
            )
        except ClientError as error:
            if self._is_missing(error):
                return None
            raise
        document = ConversationDocument.model_validate_json(response["Body"].read())
        return document, str(response["ETag"])

    async def create_conversation(self, conversation: Conversation) -> None:
        document = ConversationDocument(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            messages=[],
        )
        try:
            await asyncio.to_thread(
                self._put, self._key(conversation.id), document, IfNoneMatch="*"
            )
        except ClientError as error:
            if str(error.response.get("Error", {}).get("Code")) in {
                "PreconditionFailed",
                "412",
            }:
                raise ValueError("Conversation already exists") from error
            raise

    async def list_conversations(self) -> Sequence[Conversation]:
        def load_all() -> tuple[Conversation, ...]:
            conversations: list[Conversation] = []
            continuation_token: str | None = None
            while True:
                request: dict[str, Any] = {
                    "Bucket": self._bucket,
                    "Prefix": self._prefix,
                }
                if continuation_token is not None:
                    request["ContinuationToken"] = continuation_token
                page = self._client.list_objects_v2(**request)
                for item in page.get("Contents", []):
                    # Titles are currently fixed by the domain factory. S3's listing
                    # already contains the object key and modification time, so the
                    # navigation sidebar can avoid fetching or decrypting every
                    # transcript merely to display a list of conversations.
                    object_id = UUID(
                        str(item["Key"]).removeprefix(self._prefix).removesuffix(".json")
                    )
                    last_modified = item.get("LastModified")
                    if isinstance(last_modified, datetime):
                        conversations.append(
                            Conversation(
                                id=object_id,
                                title="New conversation",
                                created_at=last_modified,
                            )
                        )
                    else:
                        # Lightweight test doubles may omit S3's standard
                        # LastModified field; retain compatibility while real
                        # S3 avoids this fallback network read.
                        result = self._get(object_id)
                        if result is not None:
                            conversations.append(result[0].conversation())
                if not page.get("IsTruncated"):
                    break
                continuation_token = str(page["NextContinuationToken"])
            return tuple(
                sorted(conversations, key=lambda item: item.created_at, reverse=True)
            )

        return await asyncio.to_thread(load_all)

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        result = await asyncio.to_thread(self._get, conversation_id)
        return None if result is None else result[0].conversation()

    async def list_messages(self, conversation_id: UUID) -> Sequence[StoredMessage]:
        result = await asyncio.to_thread(self._get, conversation_id)
        if result is None:
            return ()
        return tuple(record.to_domain() for record in result[0].messages)

    async def append_turn(
        self, conversation_id: UUID, user: StoredMessage, assistant: StoredMessage
    ) -> None:
        if user.conversation_id != conversation_id or assistant.conversation_id != conversation_id:
            raise ValueError("Stored messages do not belong to the target conversation")

        for _ in range(3):
            result = await asyncio.to_thread(self._get, conversation_id)
            if result is None:
                raise KeyError("Conversation does not exist")
            document, etag = result
            existing_ids = {record.id for record in document.messages}
            if user.id in existing_ids and assistant.id in existing_ids:
                return
            if user.id in existing_ids or assistant.id in existing_ids:
                raise RuntimeError("Conversation contains an incomplete duplicate turn")
            updated = document.model_copy(
                update={
                    "messages": [
                        *document.messages,
                        StoredMessageRecord.from_domain(user),
                        StoredMessageRecord.from_domain(assistant),
                    ]
                }
            )
            try:
                await asyncio.to_thread(
                    self._put, self._key(conversation_id), updated, IfMatch=etag
                )
                return
            except ClientError as error:
                if str(error.response.get("Error", {}).get("Code")) not in {
                    "PreconditionFailed",
                    "412",
                }:
                    raise
        raise RuntimeError("Conversation changed repeatedly; retry the request")

    async def delete_conversation(self, conversation_id: UUID) -> bool:
        def delete_every_version() -> bool:
            """Remove and verify every recoverable version and delete marker."""

            key = self._key(conversation_id)
            found = False
            # Re-list after deletion to catch pagination changes and an append that
            # races the first pass. Persistent concurrent writers fail closed.
            for _ in range(3):
                objects: list[dict[str, Any]] = []
                key_marker: str | None = None
                version_marker: str | None = None
                while True:
                    request: dict[str, Any] = {"Bucket": self._bucket, "Prefix": key}
                    if key_marker is not None:
                        request["KeyMarker"] = key_marker
                    if version_marker is not None:
                        request["VersionIdMarker"] = version_marker
                    page = self._client.list_object_versions(**request)
                    objects.extend(
                        {"Key": item["Key"], "VersionId": item["VersionId"]}
                        for collection in (
                            page.get("Versions", []),
                            page.get("DeleteMarkers", []),
                        )
                        for item in collection
                        if item["Key"] == key
                    )
                    if not page.get("IsTruncated"):
                        break
                    key_marker = str(page["NextKeyMarker"])
                    version_marker = str(page["NextVersionIdMarker"])
                if not objects:
                    return found
                found = True
                for start in range(0, len(objects), 1000):
                    response = self._client.delete_objects(
                        Bucket=self._bucket,
                        Delete={"Objects": objects[start : start + 1000], "Quiet": True},
                    )
                    errors = response.get("Errors", [])
                    if errors:
                        raise RuntimeError(
                            f"S3 failed to delete {len(errors)} transcript version(s)"
                        )
            raise RuntimeError("Conversation changed while its S3 versions were being deleted")

        return await asyncio.to_thread(delete_every_version)
