"""Fernet-backed field encryption.

One symmetric key, loaded from the FIELD_ENCRYPTION_KEY env var (base64-encoded
per Fernet spec). The cached Fernet instance is process-wide; monkeypatching
the env var in tests requires resetting `_cached_fernet`.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet

_cached_fernet: Fernet | None = None


def _fernet() -> Fernet:
    global _cached_fernet
    if _cached_fernet is None:
        key = os.environ.get("FIELD_ENCRYPTION_KEY")
        if not key:
            raise RuntimeError("FIELD_ENCRYPTION_KEY is not set; cannot encrypt/decrypt answers")
        _cached_fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _cached_fernet


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
