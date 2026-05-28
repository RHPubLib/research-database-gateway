"""Encrypt/decrypt the per-resource launch parameters at rest.

Firestore already encrypts everything at rest with Google-managed keys. This
adds an app-layer key (Fernet / AES-128-CBC + HMAC) so that a Firestore export
or a stray backup does not, on its own, leak vendor database credentials --
the ciphertext is useless without FERNET_KEY, which lives only in Secret
Manager.

A Polaris eSource "launch parameter" is a key=value query-string fragment
appended to the database's destination URL at redirect time. Most are vendor
credentials (e.g. `password=example-pass`, `locpword=example-secret`); some are search
filters (`db=BioRC`). They are treated as a single secret-bearing blob and
encrypted together, since splitting credentials from filters reliably is not
feasible.

Plaintext exists only transiently in memory: during admin save, during the
import migration, and for the milliseconds between decrypt and 302 redirect.
"""
from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken


class CryptoError(RuntimeError):
    pass


class VendorCrypto:
    """Wraps a Fernet key. One instance is created at app startup."""

    def __init__(self, fernet_key: str):
        if not fernet_key:
            raise CryptoError("FERNET_KEY is empty")
        try:
            self._fernet = Fernet(fernet_key.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise CryptoError(
                "FERNET_KEY is not a valid Fernet key. Generate one with: "
                "python -c \"from cryptography.fernet import Fernet;"
                "print(Fernet.generate_key().decode())\""
            ) from exc

    # --- params (the new model) --------------------------------------------

    def encrypt_params(self, params: list[str]) -> str:
        """Encrypt a list of "key=value" launch-parameter strings.

        An empty list returns "" so the stored field stays empty rather than
        carrying a ciphertext that decrypts to "[]".
        """
        if not params:
            return ""
        payload = json.dumps(list(params), ensure_ascii=False).encode("utf-8")
        return self._fernet.encrypt(payload).decode("ascii")

    def decrypt_params(self, token: str) -> list[str]:
        """Decrypt a stored token back to the list of params. "" -> []."""
        if not token:
            return []
        try:
            raw = self._fernet.decrypt(token.encode("ascii"))
        except (InvalidToken, ValueError) as exc:
            raise CryptoError(
                "could not decrypt launch parameters -- FERNET_KEY may have "
                "changed since this record was saved"
            ) from exc
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CryptoError("decrypted launch-params payload is not valid JSON") from exc
        if not isinstance(data, list) or not all(isinstance(p, str) for p in data):
            raise CryptoError("decrypted launch-params payload is not a list[str]")
        return data
