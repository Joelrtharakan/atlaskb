"""API keys: create, list, revoke — scoped to the caller's active tenant.

A key authenticates programmatic access to /chat and /search via the
``X-API-Key`` header. Its role cannot exceed the creator's role in the tenant.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_principal
from app.logging_config import get_logger
from app.models import ApiKey
from app.rbac import Principal, role_at_least
from app.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from app.security import generate_api_key

router = APIRouter(prefix="/api-keys", tags=["api-keys"])
log = get_logger(__name__)


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
def create_api_key(
    body: ApiKeyCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> ApiKeyCreated:
    # API keys must be minted with an interactive login, not another API key.
    if principal.auth != "jwt":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Create API keys from an interactive session, not with a key."
        )

    role = body.role or principal.role
    if not role_at_least(principal.role, role):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"You cannot issue a key with a higher role ('{role}') than your own ('{principal.role}').",
        )

    full_key, lookup, key_hash = generate_api_key()
    key = ApiKey(
        workspace_id=principal.workspace_id,
        user_id=principal.user_id,
        name=body.name,
        role=role,
        lookup=lookup,
        key_hash=key_hash,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    log.info("apikey.create", workspace_id=principal.workspace_id, key_id=key.id, role=role)
    return ApiKeyCreated(
        id=key.id,
        name=key.name,
        role=key.role,
        lookup=key.lookup,
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        revoked_at=key.revoked_at,
        key=full_key,
    )


@router.get("", response_model=list[ApiKeyOut])
def list_api_keys(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> list[ApiKey]:
    stmt = select(ApiKey).where(ApiKey.workspace_id == principal.workspace_id)
    # Admins see all tenant keys; others see only their own.
    if not principal.is_admin:
        stmt = stmt.where(ApiKey.user_id == principal.user_id)
    return list(db.scalars(stmt.order_by(ApiKey.created_at.desc())))


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> None:
    key = db.get(ApiKey, key_id)
    # Never confirm existence of keys outside the caller's tenant.
    if key is None or key.workspace_id != principal.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")
    if not principal.is_admin and key.user_id != principal.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only revoke your own API keys.")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        db.commit()
    log.info("apikey.revoke", workspace_id=principal.workspace_id, key_id=key.id)
