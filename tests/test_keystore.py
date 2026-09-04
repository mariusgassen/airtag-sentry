import pytest
from cryptography.fernet import Fernet, InvalidToken

from airtag_sentry.keystore import decrypt, encrypt


def test_encrypt_decrypt_round_trip():
    key = Fernet.generate_key().decode()
    token = encrypt(key, "super-secret-key-material")
    assert decrypt(key, token) == "super-secret-key-material"


def test_decrypt_with_wrong_key_raises():
    key = Fernet.generate_key().decode()
    other_key = Fernet.generate_key().decode()
    token = encrypt(key, "super-secret-key-material")
    with pytest.raises(InvalidToken):
        decrypt(other_key, token)
