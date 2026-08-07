"""Authentication endpoints: signup, login, refresh."""

from __future__ import annotations

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.logging_config import get_logger
from app.models import ROLE_ADMIN, Tenant, TenantMembership, User
from app.schemas import LoginRequest, RefreshRequest, SignupRequest, TokenPair, UserOut
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger(__name__)


def _tokens_for(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> User:
    existing = db.scalar(select(User).where(User.email == body.email))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    # Every user gets a personal workspace (tenant) they administer. This is
    # their default tenant when no X-Tenant-Id is supplied.
    tenant = Tenant(name=f"{body.email}'s workspace")
    db.add(tenant)
    db.flush()

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        tenant_id=tenant.id,
    )
    db.add(user)
    db.flush()

    db.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, role=ROLE_ADMIN))
    db.commit()
    db.refresh(user)
    log.info("auth.signup", user_id=user.id, email=user.email, tenant_id=tenant.id)
    return user


@router.post("/login", response_model=TokenPair)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenPair:
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        # Same error whether the email is unknown or the password is wrong.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    log.info("auth.login", user_id=user.id)
    return _tokens_for(user)


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)) -> TokenPair:
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    user = db.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    log.info("auth.refresh", user_id=user.id)
    return _tokens_for(user)
