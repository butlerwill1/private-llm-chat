import pytest
from cryptography.exceptions import InvalidTag

from private_chat.adapters.encryption import AesGcmEnvelopeEncryptor, LocalAesDataKeyProvider


def test_round_trip_and_context_binding() -> None:
    encryptor = AesGcmEnvelopeEncryptor(LocalAesDataKeyProvider(b"k" * 32))
    encrypted = encryptor.encrypt(b"secret", context=b"record-a")

    assert encryptor.decrypt(encrypted, context=b"record-a") == b"secret"
    with pytest.raises(InvalidTag):
        encryptor.decrypt(encrypted, context=b"record-b")


def test_each_encryption_uses_fresh_ciphertext_and_wrapped_key() -> None:
    encryptor = AesGcmEnvelopeEncryptor(LocalAesDataKeyProvider(b"k" * 32))
    first = encryptor.encrypt(b"same", context=b"record")
    second = encryptor.encrypt(b"same", context=b"record")
    assert first.ciphertext != second.ciphertext
    assert first.wrapped_data_key != second.wrapped_data_key

