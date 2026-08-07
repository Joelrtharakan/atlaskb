"""Shared FastAPI dependencies: user auth, tenant/role resolution, API keys."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ApiKey, User
from app.rbac import Principal, get_membership, role_at_least
from app.security import api_key_lookup, decode_token, hash_api_key

_bearer = HTTPBearer(auto_error=True)

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from a Bearer access token (no tenant)."""
    try:
        payload = decode_token(creds.credentials, expected_type="access")
    except jwt.PyJWTError:
        raise _CREDENTIALS_ERROR

    user_id = payload.get("sub")
    if not user_id:
        raise _CREDENTIALS_ERROR
    user = db.get(User, user_id)
    if user is None:
        raise _CREDENTIALS_ERROR
    return user


def _principal_from_api_key(db: Session, presented: str) -> Principal:
    lookup = api_key_lookup(presented)
    if not lookup:
        raise _CREDENTIALS_ERROR
    key = db.scalar(
        select(ApiKey).where(ApiKey.lookup == lookup, ApiKey.revoked_at.is_(None))
    )
    if key is None or hash_api_key(presented) != key.key_hash:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked API key")
    key.last_used_at = datetime.now(UTC)
    db.commit()
    return Principal(user_id=key.user_id, tenant_id=key.tenant_id, role=key.role, auth="api_key")


def get_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    """Resolve the acting principal (user + tenant + role).

    Two auth methods are accepted:
      * ``X-API-Key: atlk_...`` — tenant and role fixed by the key.
      * ``Authorization: Bearer <jwt>`` — tenant chosen by the optional
        ``X-Tenant-Id`` header, defaulting to the user's personal tenant. The
        user must be a member of the selected tenant.
    """
    api_key = request.headers.get("x-api-key")
    if api_key:
        return _principal_from_api_key(db, api_key)

    auth_header = request.headers.get("authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _CREDENTIALS_ERROR
    try:
        payload = decode_token(token, expected_type="access")
    except jwt.PyJWTError:
        raise _CREDENTIALS_ERROR

    user = db.get(User, payload.get("sub"))
    if user is None:
        raise _CREDENTIALS_ERROR

    tenant_id = request.headers.get("x-tenant-id") or user.tenant_id
    membership = get_membership(db, tenant_id, user.id)
    if membership is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You are not a member of this workspace."
        )
    return Principal(user_id=user.id, tenant_id=tenant_id, role=membership.role, auth="jwt")


def require_role(minimum: str) -> Callable[..., Principal]:
    """Dependency factory: require the principal's role be at least ``minimum``."""

    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if not role_at_least(principal.role, minimum):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"This action requires the '{minimum}' role or higher in this workspace.",
            )
        return principal

    return dependency
