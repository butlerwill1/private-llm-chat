import os
from hashlib import sha256

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from private_chat.domain.models import EncryptedPayload
from private_chat.ports.interfaces import DataKeyProvider


class AesGcmEnvelopeEncryptor:
    """Encrypts each value with a unique data key and authenticated context."""

    def __init__(self, data_keys: DataKeyProvider) -> None:
        self._data_keys = data_keys

    def encrypt(self, plaintext: bytes, *, context: bytes) -> EncryptedPayload:
        data_key, wrapped_key, key_id = self._data_keys.generate_data_key(context=context)
        try:
            nonce = os.urandom(12)
            ciphertext = AESGCM(data_key).encrypt(nonce, plaintext, context)
            return EncryptedPayload(ciphertext, nonce, wrapped_key, key_id)
        finally:
            # Python cannot guarantee zeroisation of immutable bytes. Keeping the key in a
            # narrow scope still reduces accidental retention; production wrapping belongs in KMS.
            del data_key

    def decrypt(self, payload: EncryptedPayload, *, context: bytes) -> bytes:
        if payload.algorithm != "AES-256-GCM":
            raise ValueError("Unsupported encryption algorithm")
        data_key = self._data_keys.unwrap_data_key(
            payload.wrapped_data_key, key_id=payload.key_id, context=context
        )
        try:
            return AESGCM(data_key).decrypt(payload.nonce, payload.ciphertext, context)
        finally:
            del data_key


class LocalAesDataKeyProvider:
    """Local key wrapper for development/tests; replace with an AWS KMS adapter in production."""

    def __init__(self, master_key: bytes) -> None:
        if len(master_key) != 32:
            raise ValueError("Local master key must contain exactly 32 bytes")
        self._master_key = master_key
        self.key_id = f"local-aes-v1:{sha256(master_key).hexdigest()[:16]}"

    def generate_data_key(self, *, context: bytes) -> tuple[bytes, bytes, str]:
        data_key = os.urandom(32)
        nonce = os.urandom(12)
        wrapped = nonce + AESGCM(self._master_key).encrypt(nonce, data_key, context)
        return data_key, wrapped, self.key_id

    def unwrap_data_key(self, wrapped_data_key: bytes, *, key_id: str, context: bytes) -> bytes:
        if key_id != self.key_id:
            raise ValueError("Unknown local key identifier")
        if len(wrapped_data_key) < 13:
            raise ValueError("Invalid wrapped data key")
        return AESGCM(self._master_key).decrypt(
            wrapped_data_key[:12], wrapped_data_key[12:], context
        )
