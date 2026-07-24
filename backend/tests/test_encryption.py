"""Security-property tests for local AES-GCM envelope encryption."""

import pytest
from cryptography.exceptions import InvalidTag

from private_chat.adapters.encryption import AesGcmEnvelopeEncryptor, LocalAesDataKeyProvider


def test_round_trip_and_context_binding() -> None:
    """Ciphertext decrypts only when supplied with its original record context.

    AES-GCM authenticates the context as additional data. A transcript record
    copied to a different identity must therefore fail authentication even when
    its ciphertext and wrapped key are otherwise intact.
    """

    # Arrange: build the encryption service with a deterministic 32-byte local
    # master key. Production S3 mode replaces this provider with AWS KMS.
    encryptor = AesGcmEnvelopeEncryptor(LocalAesDataKeyProvider(b"k" * 32))
    # Act: encrypt six plaintext bytes and authenticate the record identifier as
    # additional data. The context is checked but is not stored inside ciphertext.
    encrypted = encryptor.encrypt(b"secret", context=b"record-a")

    # Assert the normal round trip first, using the exact same context.
    assert encryptor.decrypt(encrypted, context=b"record-a") == b"secret"
    # InvalidTag proves that record-a ciphertext cannot be replayed as record-b.
    with pytest.raises(InvalidTag):
        encryptor.decrypt(encrypted, context=b"record-b")


def test_each_encryption_uses_fresh_ciphertext_and_wrapped_key() -> None:
    """Repeated plaintext must use fresh nonces and per-record data keys.

    Different ciphertext prevents equality leakage, while different wrapped
    keys demonstrates that envelope encryption is not reusing one data key.
    """

    # Arrange one encryptor so differences cannot be attributed to configuration.
    encryptor = AesGcmEnvelopeEncryptor(LocalAesDataKeyProvider(b"k" * 32))
    # Act twice with identical plaintext and context. Secure random nonces and
    # per-message keys should still make the results different.
    first = encryptor.encrypt(b"same", context=b"record")
    second = encryptor.encrypt(b"same", context=b"record")
    # Compare the encrypted values directly; plaintext equality must not leak as
    # equality of either ciphertext or wrapped data keys.
    assert first.ciphertext != second.ciphertext
    assert first.wrapped_data_key != second.wrapped_data_key
