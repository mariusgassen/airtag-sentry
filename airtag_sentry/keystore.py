"""Symmetric encryption for AirTag key material stored at rest in Postgres.

The encryption key itself lives in the environment (AIRTAG_KEY_ENCRYPTION_KEY) -
a secret used to encrypt other secrets can't itself live in the store it protects.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

__all__ = ["InvalidToken", "encrypt", "decrypt"]


def encrypt(encryption_key: str, plaintext: str) -> str:
    return Fernet(encryption_key.encode()).encrypt(plaintext.encode()).decode()


def decrypt(encryption_key: str, token: str) -> str:
    return Fernet(encryption_key.encode()).decrypt(token.encode()).decode()
