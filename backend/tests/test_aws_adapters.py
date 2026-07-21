import base64
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

import pytest
from botocore.exceptions import ClientError

from private_chat.adapters.aws_kms import KmsDataKeyProvider
from private_chat.adapters.s3_repository import S3ConversationRepository
from private_chat.domain.models import Conversation, EncryptedPayload, Role, StoredMessage


def client_error(code: str, operation: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


class FakeS3:
    """Small stateful S3 double covering the conditional repository contract."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str, str]] = {}
        self.version_counter = 0

    def put_object(self, **request: Any) -> None:
        key = str(request["Key"])
        current = self.objects.get(key)
        if request.get("IfNoneMatch") == "*" and current is not None:
            raise client_error("PreconditionFailed", "PutObject")
        if "IfMatch" in request and (current is None or request["IfMatch"] != current[1]):
            raise client_error("PreconditionFailed", "PutObject")
        self.version_counter += 1
        etag = f'"etag-{self.version_counter}"'
        self.objects[key] = (bytes(request["Body"]), etag, str(self.version_counter))

    def get_object(self, **request: Any) -> dict[str, Any]:
        key = str(request["Key"])
        if key not in self.objects:
            raise client_error("NoSuchKey", "GetObject")
        body, etag, _ = self.objects[key]
        return {"Body": BytesIO(body), "ETag": etag}

    def list_objects_v2(self, **request: Any) -> dict[str, Any]:
        prefix = str(request["Prefix"])
        return {
            "Contents": [{"Key": key} for key in self.objects if key.startswith(prefix)],
            "IsTruncated": False,
        }

    def list_object_versions(self, **request: Any) -> dict[str, Any]:
        prefix = str(request["Prefix"])
        return {
            "Versions": [
                {"Key": key, "VersionId": version}
                for key, (_, _, version) in self.objects.items()
                if key.startswith(prefix)
            ],
            "DeleteMarkers": [],
            "IsTruncated": False,
        }

    def delete_objects(self, **request: Any) -> dict[str, Any]:
        for item in request["Delete"]["Objects"]:
            self.objects.pop(str(item["Key"]), None)
        return {"Errors": []}


@pytest.mark.asyncio
async def test_s3_repository_round_trip_and_permanent_delete() -> None:
    client = FakeS3()
    repository = S3ConversationRepository(client, "private-bucket", "kms-key")
    conversation = Conversation.create()
    payload = EncryptedPayload(
        ciphertext=b"ciphertext",
        nonce=b"n" * 12,
        wrapped_data_key=b"wrapped-key",
        key_id="kms-key",
    )
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

    await repository.create_conversation(conversation)
    await repository.append_turn(conversation.id, user, assistant)

    assert await repository.get_conversation(conversation.id) == conversation
    assert [item.id for item in await repository.list_messages(conversation.id)] == [
        user.id,
        assistant.id,
    ]
    assert (await repository.list_conversations())[0] == conversation
    stored_json = next(iter(client.objects.values()))[0]
    assert base64.b64encode(payload.ciphertext) in stored_json
    assert await repository.delete_conversation(conversation.id) is True
    assert client.objects == {}
    assert await repository.delete_conversation(conversation.id) is False


@pytest.mark.asyncio
async def test_s3_delete_fails_closed_on_partial_failure() -> None:
    class PartiallyFailingS3(FakeS3):
        def delete_objects(self, **request: Any) -> dict[str, Any]:
            return {"Errors": [{"Key": request["Delete"]["Objects"][0]["Key"]}]}

    client = PartiallyFailingS3()
    repository = S3ConversationRepository(client, "private-bucket", "kms-key")
    conversation = Conversation.create()
    await repository.create_conversation(conversation)

    with pytest.raises(RuntimeError, match="failed to delete"):
        await repository.delete_conversation(conversation.id)
    assert await repository.get_conversation(conversation.id) == conversation


class FakeKms:
    def __init__(self) -> None:
        self.context: dict[str, str] | None = None

    def generate_data_key(self, **request: Any) -> dict[str, Any]:
        self.context = request["EncryptionContext"]
        return {"Plaintext": b"p" * 32, "CiphertextBlob": b"wrapped", "KeyId": "key/123"}

    def decrypt(self, **request: Any) -> dict[str, Any]:
        assert request["EncryptionContext"] == self.context
        return {"Plaintext": b"p" * 32}


def test_kms_data_keys_preserve_authenticated_context() -> None:
    client = FakeKms()
    provider = KmsDataKeyProvider(client, "key/123")
    plaintext, wrapped, key_id = provider.generate_data_key(context=b"conversation=one")

    assert plaintext == b"p" * 32
    assert provider.unwrap_data_key(
        wrapped, key_id=key_id, context=b"conversation=one"
    ) == plaintext
    assert client.context == {"private-chat-record": "conversation=one"}
