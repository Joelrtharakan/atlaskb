"""Authentication endpoints: signup, login, refresh."""

from __future__ import annotations

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.logging_config import get_logger
from app.models import User
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

    # A user account is separate from a workspace: on signup the user has no
    # workspace. They must create one (POST /workspaces) or accept an invite.
    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    log.info("auth.signup", user_id=user.id, email=user.email)
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
