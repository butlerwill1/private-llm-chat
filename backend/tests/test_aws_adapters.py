"""Offline contract tests for the S3 repository and AWS KMS data-key adapter.

The fakes model only the AWS behaviours the adapters rely on: conditional ETags,
object versions, partial bulk-delete failures and KMS encryption context. This
keeps the suite fast while documenting the assumptions that live integration
tests should verify against an AWS account.
"""

import base64
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

import pytest
from botocore.exceptions import ClientError

from private_chat.adapters.aws_kms import KmsDataKeyProvider
from private_chat.adapters.encryption import AesGcmEnvelopeEncryptor, LocalAesDataKeyProvider
from private_chat.adapters.s3_repository import ConversationDocument, S3ConversationRepository
from private_chat.domain.models import Conversation, EncryptedPayload, Role, StoredMessage


def repository_for(client: Any) -> S3ConversationRepository:
    return S3ConversationRepository(
        client,
        "private-bucket",
        "kms-key",
        AesGcmEnvelopeEncryptor(LocalAesDataKeyProvider(b"s" * 32)),
    )


def client_error(code: str, operation: str) -> ClientError:
    """Construct a realistic Botocore error for fake AWS failure paths."""

    # Botocore clients raise ClientError with a structured AWS response and the
    # operation name; matching that shape exercises production exception handling.
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


class FakeS3:
    """Small stateful S3 double covering the conditional repository contract.

    Each stored tuple contains the serialised body, current ETag and version ID.
    It is intentionally narrower than S3 and should grow only when production
    code starts depending on another documented AWS behaviour.
    """

    def __init__(self) -> None:
        # Map each S3 object key to (body bytes, ETag, version ID).
        self.objects: dict[str, tuple[bytes, str, str]] = {}
        # Incrementing this counter gives every successful write a new identity.
        self.version_counter = 0

    def put_object(self, **request: Any) -> None:
        """Apply S3-style create/update preconditions and store a new version."""

        # **request receives the same keyword argument dictionary boto3 would.
        key = str(request["Key"])
        current = self.objects.get(key)
        # IfNoneMatch="*" means creation must fail when an object already exists.
        if request.get("IfNoneMatch") == "*" and current is not None:
            raise client_error("PreconditionFailed", "PutObject")
        # IfMatch permits an update only when the caller read the current ETag.
        if "IfMatch" in request and (current is None or request["IfMatch"] != current[1]):
            raise client_error("PreconditionFailed", "PutObject")
        self.version_counter += 1
        etag = f'"etag-{self.version_counter}"'
        # bytes(...) normalises boto3's Body value before the fake stores it.
        self.objects[key] = (bytes(request["Body"]), etag, str(self.version_counter))

    def get_object(self, **request: Any) -> dict[str, Any]:
        """Return a streaming body and ETag, or S3's missing-key error."""

        key = str(request["Key"])
        # Mirror S3 by raising a structured error rather than returning None.
        if key not in self.objects:
            raise client_error("NoSuchKey", "GetObject")
        # The underscore intentionally discards the version ID in this operation.
        body, etag, _ = self.objects[key]
        # BytesIO supplies the .read() interface returned by real boto3 streaming bodies.
        return {"Body": BytesIO(body), "ETag": etag}

    def list_objects_v2(self, **request: Any) -> dict[str, Any]:
        """List current objects below the repository's conversation prefix."""

        prefix = str(request["Prefix"])
        return {
            # Include only keys under the requested prefix, as list_objects_v2 does.
            "Contents": [{"Key": key} for key in self.objects if key.startswith(prefix)],
            "IsTruncated": False,
        }

    def list_object_versions(self, **request: Any) -> dict[str, Any]:
        """Expose recoverable versions used by permanent transcript deletion."""

        prefix = str(request["Prefix"])
        return {
            # Convert the fake's tuples into boto3-shaped version dictionaries.
            "Versions": [
                {"Key": key, "VersionId": version}
                for key, (_, _, version) in self.objects.items()
                if key.startswith(prefix)
            ],
            "DeleteMarkers": [],
            "IsTruncated": False,
        }

    def delete_objects(self, **request: Any) -> dict[str, Any]:
        """Delete requested versions and report no per-object failures."""

        # Each item identifies a key and version. The simplified fake stores only
        # one current tuple per key, so removing the key represents permanent erase.
        for item in request["Delete"]["Objects"]:
            self.objects.pop(str(item["Key"]), None)
        return {"Errors": []}


@pytest.mark.asyncio
async def test_s3_repository_round_trip_and_permanent_delete() -> None:
    """S3 persistence should round-trip metadata/messages and erase all versions.

    This exercises creation, optimistic append, listing, binary JSON encoding and
    privacy-sensitive permanent deletion through the repository interface.
    """

    # Arrange the fake boto3 client and inject it into the real repository adapter.
    client = FakeS3()
    repository = repository_for(client)
    conversation = Conversation.create()
    # The repository receives already-encrypted payloads. Fixed bytes make their
    # serialised base64 form easy to locate later in the stored JSON document.
    payload = EncryptedPayload(
        ciphertext=b"ciphertext",
        nonce=b"n" * 12,
        wrapped_data_key=b"wrapped-key",
        key_id="kms-key",
    )
    # Both messages share a timestamp only to keep setup compact; their UUIDs and
    # roles still make them distinct records in one conversation.
    now = datetime.now(UTC)
    user = StoredMessage(
        id=conversation.id,
        conversation_id=conversation.id,
        role=Role.USER,
        encrypted_content=payload,
        created_at=now,
    )
    assistant = StoredMessage(
        id=Conversation.create().id,
        conversation_id=conversation.id,
        role=Role.ASSISTANT,
        encrypted_content=payload,
        created_at=now,
    )

    # Act: create an empty document and conditionally append a complete turn.
    await repository.create_conversation(conversation)
    await repository.append_turn(conversation.id, user, assistant)
    await repository.rename_conversation(conversation.id, "Private reflections")

    # Domain objects reconstructed from S3 must retain identity and message order.
    renamed = await repository.get_conversation(conversation.id)
    assert renamed is not None
    assert renamed.title == "Private reflections"
    assert [item.id for item in await repository.list_messages(conversation.id)] == [
        user.id,
        assistant.id,
    ]
    assert (await repository.list_conversations())[0].title == "Private reflections"
    # The fake has one object. iter(...), next(...) selects its tuple, and [0]
    # selects the raw body bytes from (body, ETag, version ID).
    stored_json = next(iter(client.objects.values()))[0]
    # Binary ciphertext is represented safely in JSON rather than decoded or lost.
    assert base64.b64encode(payload.ciphertext) in stored_json
    assert b"Private reflections" not in stored_json
    # True means data existed and was removed; the second call returning False
    # establishes idempotent behaviour once no recoverable versions remain.
    assert await repository.delete_conversation(conversation.id) is True
    assert client.objects == {}
    assert await repository.delete_conversation(conversation.id) is False


@pytest.mark.asyncio
async def test_s3_delete_fails_closed_on_partial_failure() -> None:
    """An HTTP-successful S3 bulk delete must fail if any object reports an error.

    S3 can return a 200 response with a populated ``Errors`` collection. Ignoring
    that detail could tell the user deletion succeeded while a transcript version
    remained recoverable.
    """

    class PartiallyFailingS3(FakeS3):
        """S3 double that reports the first requested version as undeleted."""

        def delete_objects(self, **request: Any) -> dict[str, Any]:
            # Real S3 may return HTTP 200 yet put failed items in this Errors list.
            return {"Errors": [{"Key": request["Delete"]["Objects"][0]["Key"]}]}

    # Arrange one existing object so the repository has a version to delete.
    client = PartiallyFailingS3()
    repository = repository_for(client)
    conversation = Conversation.create()
    await repository.create_conversation(conversation)

    # Act and Assert: the adapter must inspect Errors and surface the partial
    # failure. Matching the message protects against an unrelated RuntimeError.
    with pytest.raises(RuntimeError, match="failed to delete"):
        await repository.delete_conversation(conversation.id)
    # The fake deliberately retains the object, demonstrating why the adapter
    # must surface the failure instead of returning a successful deletion result.
    assert await repository.get_conversation(conversation.id) == conversation


@pytest.mark.asyncio
async def test_s3_repository_migrates_legacy_plaintext_title() -> None:
    client = FakeS3()
    repository = repository_for(client)
    conversation = Conversation.create("Legacy private title")
    legacy_document = ConversationDocument(
        schema_version=2,
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        messages=[],
    )
    client.put_object(
        Bucket="private-bucket",
        Key=S3ConversationRepository._key(conversation.id),
        Body=legacy_document.model_dump_json().encode(),
    )

    migrated = await repository.get_conversation(conversation.id)
    assert migrated is not None
    assert migrated.title == "Legacy private title"
    stored_json = next(iter(client.objects.values()))[0]
    assert b"Legacy private title" not in stored_json


class FakeKms:
    """KMS double that records authenticated encryption context across operations."""

    def __init__(self) -> None:
        # None means no generate_data_key call has been observed yet.
        self.context: dict[str, str] | None = None

    def generate_data_key(self, **request: Any) -> dict[str, Any]:
        """Return deterministic key material and remember the supplied context."""

        self.context = request["EncryptionContext"]
        # Plaintext represents the usable AES key; CiphertextBlob is the same key
        # wrapped by KMS and safe to store alongside encrypted application data.
        return {"Plaintext": b"p" * 32, "CiphertextBlob": b"wrapped", "KeyId": "key/123"}

    def decrypt(self, **request: Any) -> dict[str, Any]:
        """Require unwrap to repeat the exact context used when generating the key."""

        # This assertion lives in the fake so the test fails at the exact boundary
        # if the adapter changes or omits context during unwrap.
        assert request["EncryptionContext"] == self.context
        return {"Plaintext": b"p" * 32}


def test_kms_data_keys_preserve_authenticated_context() -> None:
    """KMS generate/unwrap calls must bind a data key to its transcript record.

    Preserving the encryption context stops wrapped keys being moved between
    records without detection and verifies the adapter's byte/string conversion.
    """

    # Arrange a provider around the fake client and one configured KMS key ID.
    client = FakeKms()
    provider = KmsDataKeyProvider(client, "key/123")
    # Act: tuple unpacking names the three values returned by GenerateDataKey.
    plaintext, wrapped, key_id = provider.generate_data_key(context=b"conversation=one")

    # Assert the plaintext is usable and the wrapped value can be unwrapped only
    # while repeating the same configured key and authenticated record context.
    assert plaintext == b"p" * 32
    assert provider.unwrap_data_key(
        wrapped, key_id=key_id, context=b"conversation=one"
    ) == plaintext
    assert client.context == {"private-chat-record": "conversation=one"}
