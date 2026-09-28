"""Application-level encryption for PII columns.

`document_number` holds KYC identifiers (Aadhaar / passport numbers). Storing
those in plaintext means anyone with a database file -- a stolen laptop, a leaked
backup, a misconfigured volume -- has the identity documents of every registered
tourist. They are encrypted at rest here.

The key is derived from SECRET_KEY so there is no second secret to manage. That
also means rotating SECRET_KEY makes existing ciphertext unreadable; the
decryptor returns a placeholder rather than raising, so a key change degrades the
display of old records instead of breaking every endpoint that reads a tourist.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String, TypeDecorator

from app.core.config import settings

_PREFIX = "enc:v1:"
UNREADABLE = "<unreadable: key rotated>"


def _fernet() -> Fernet:
    # Fernet needs a 32-byte urlsafe-base64 key; derive one deterministically.
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    return _PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    if not value.startswith(_PREFIX):
        # Pre-encryption row, or seed data written before this landed.
        return value
    try:
        return _fernet().decrypt(value[len(_PREFIX):].encode()).decode()
    except InvalidToken:
        return UNREADABLE


class EncryptedString(TypeDecorator):
    """Transparently encrypts on write and decrypts on read.

    Applied at the column level so every read path -- API serialisation, the
    E-FIR generator, the hash chain -- gets the plaintext without each one having
    to remember to decrypt. Note this makes the column unsearchable by value,
    which is fine: nothing queries by document number.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else encrypt(value)

    def process_result_value(self, value, dialect):
        return None if value is None else decrypt(value)
