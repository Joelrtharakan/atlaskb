"""Password hashing (argon2), JWT issue/verify, and API-key helpers."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config import settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _create_token(subject: str, token_type: str, expires: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str) -> str:
    return _create_token(
        user_id, "access", timedelta(minutes=settings.access_token_ttl_minutes)
    )


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        user_id, "refresh", timedelta(days=settings.refresh_token_ttl_days)
    )


def decode_token(token: str, *, expected_type: str) -> dict:
    """Decode and validate a JWT, raising jwt exceptions on failure.

    Enforces the token ``type`` so a refresh token cannot be used where an
    access token is required, and vice versa.
    """
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected {expected_type} token")
    return payload


# --- API keys ---
# Keys are high-entropy random tokens, so a fast SHA-256 of the full key is
# sufficient (unlike passwords, they are not guessable). We store the hash plus
# a plaintext ``lookup`` prefix used to find the row before verifying.
def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Return ``(full_key, lookup, key_hash)``. ``full_key`` is shown once."""
    secret = secrets.token_urlsafe(32)
    full = f"{settings.api_key_prefix}_{secret}"
    lookup = secret[: settings.api_key_lookup_len]
    return full, lookup, _sha256(full)


def api_key_lookup(full_key: str) -> str | None:
    """Extract the lookup prefix from a presented key, or None if malformed."""
    parts = full_key.split("_", 1)
    if len(parts) != 2 or not parts[1]:
        return None
    return parts[1][: settings.api_key_lookup_len]


def hash_api_key(full_key: str) -> str:
    return _sha256(full_key)


def generate_invite_token() -> str:
    """A high-entropy, URL-safe invite token."""
    return secrets.token_urlsafe(32)
