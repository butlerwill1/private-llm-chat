"""AWS KMS implementation of the application's data-key boundary."""

from typing import Any


class KmsDataKeyProvider:
    """Generate and unwrap per-message AES keys using a customer-managed KMS key."""

    def __init__(self, client: Any, key_id: str) -> None:
        self._client = client
        self._key_id = key_id

    @staticmethod
    def _encryption_context(context: bytes) -> dict[str, str]:
        return {"private-chat-record": context.decode("ascii")}

    def generate_data_key(self, *, context: bytes) -> tuple[bytes, bytes, str]:
        response = self._client.generate_data_key(
            KeyId=self._key_id,
            KeySpec="AES_256",
            EncryptionContext=self._encryption_context(context),
        )
        plaintext = bytes(response["Plaintext"])
        ciphertext = bytes(response["CiphertextBlob"])
        returned_key_id = str(response["KeyId"])
        if len(plaintext) != 32:
            raise RuntimeError("AWS KMS returned an invalid AES-256 data key")
        return plaintext, ciphertext, returned_key_id

    def unwrap_data_key(
        self, wrapped_data_key: bytes, *, key_id: str, context: bytes
    ) -> bytes:
        if key_id != self._key_id and not key_id.endswith(self._key_id.rsplit("/", 1)[-1]):
            raise ValueError("Wrapped data key does not belong to the configured KMS key")
        response = self._client.decrypt(
            CiphertextBlob=wrapped_data_key,
            KeyId=self._key_id,
            EncryptionContext=self._encryption_context(context),
        )
        plaintext = bytes(response["Plaintext"])
        if len(plaintext) != 32:
            raise RuntimeError("AWS KMS returned an invalid unwrapped AES-256 key")
        return plaintext
