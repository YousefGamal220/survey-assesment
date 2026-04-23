from __future__ import annotations

import pytest
from cryptography.fernet import Fernet, InvalidToken

from apps.responses.crypto import decrypt, encrypt


class TestCrypto:
    def test_round_trip(self):
        plain = "+1 (555) 000-1234"
        cipher = encrypt(plain)
        assert cipher != plain
        assert decrypt(cipher) == plain

    def test_ciphertext_is_non_deterministic(self):
        """Fernet bakes a random IV into each encrypt() — two calls on the same
        plaintext must return different ciphertexts so a passive observer can't
        link equal-valued rows."""
        a = encrypt("same")
        b = encrypt("same")
        assert a != b
        assert decrypt(a) == decrypt(b) == "same"

    def test_wrong_key_cannot_decrypt(self, monkeypatch):
        good_cipher = encrypt("secret")
        # Flip to a freshly generated key and verify decrypt refuses
        bad_key = Fernet.generate_key().decode()
        monkeypatch.setattr("apps.responses.crypto._cached_fernet", None)
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY", bad_key)
        with pytest.raises(InvalidToken):
            decrypt(good_cipher)

    def test_empty_string_round_trip(self):
        assert decrypt(encrypt("")) == ""
