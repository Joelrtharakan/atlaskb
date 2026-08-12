"""Encrypts/decrypts a connector's provider credentials for storage in
``ConnectorConfig.credentials_ref``.

``credentials_ref`` is documented (see ``app.models.ConnectorConfig``) as an
opaque reference a real provider resolves itself, deliberately never a
plaintext secret. This is that resolution for the Google Drive connector:
the refresh token (plus any small provider-specific config, e.g. which
Drive folder to scope to) is JSON-encoded then Fernet-encrypted, keyed by
``settings.connector_token_key`` — a key that lives only in the
environment, never in the database or source.
"""

from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class TokenStorageError(Exception):
    """Raised when CONNECTOR_TOKEN_KEY is unset or stored credentials can't
    be decrypted (e.g. the key changed) — callers must treat this as the
    connector needing to be reconnected, not a transient failure."""


def _fernet() -> Fernet:
    if not settings.connector_token_key:
        raise TokenStorageError(
            "CONNECTOR_TOKEN_KEY is not set — required to store connector credentials. "
            "See .env.example."
        )
    try:
        return Fernet(settings.connector_token_key.encode())
    except (ValueError, TypeError) as exc:
        raise TokenStorageError(f"CONNECTOR_TOKEN_KEY is not a valid Fernet key: {exc}") from exc


def encrypt_credentials(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_credentials(credentials_ref: str) -> dict:
    try:
        raw = _fernet().decrypt(credentials_ref.encode())
    except InvalidToken as exc:
        raise TokenStorageError("Stored connector credentials could not be decrypted.") from exc
    return json.loads(raw)
