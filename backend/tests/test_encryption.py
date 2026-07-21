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

    encryptor = AesGcmEnvelopeEncryptor(LocalAesDataKeyProvider(b"k" * 32))
    encrypted = encryptor.encrypt(b"secret", context=b"record-a")

    assert encryptor.decrypt(encrypted, context=b"record-a") == b"secret"
    # InvalidTag proves that record-a ciphertext cannot be replayed as record-b.
    with pytest.raises(InvalidTag):
        encryptor.decrypt(encrypted, context=b"record-b")


def test_each_encryption_uses_fresh_ciphertext_and_wrapped_key() -> None:
    """Repeated plaintext must use fresh nonces and per-record data keys.

    Different ciphertext prevents equality leakage, while different wrapped
    keys demonstrates that envelope encryption is not reusing one data key.
    """

    encryptor = AesGcmEnvelopeEncryptor(LocalAesDataKeyProvider(b"k" * 32))
    first = encryptor.encrypt(b"same", context=b"record")
    second = encryptor.encrypt(b"same", context=b"record")
    assert first.ciphertext != second.ciphertext
    assert first.wrapped_data_key != second.wrapped_data_key
