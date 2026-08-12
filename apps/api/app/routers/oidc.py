"""SSO login via generic OIDC (Trust Layer Phase 11).

Mirrors the Google Drive connector's OAuth shape (``app/routers/connectors.py``)
for the authorize/callback split — a signed, short-lived ``state`` JWT
carries CSRF/nonce/PKCE context across the redirect, since authorize and
callback are two separate, unauthenticated requests with nothing else
tying them together.

One further hop beyond the connector flow: the callback can't hand tokens
back to the frontend as a JSON response (it's a top-level browser redirect,
not a fetch), and putting access/refresh tokens directly in a redirect URL
would leak them into browser history and any referrer headers. Instead the
callback mints a one-time, Redis-backed exchange code (60s TTL, deleted on
first use) and redirects with only that in the URL; the frontend's callback
page immediately exchanges it for the real ``TokenPair`` via a POST.
"""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.logging_config import get_logger
from app.models import User, UserIdentity
from app.oidc import OIDCClaims, OIDCError, authorization_url, exchange_code
from app.redis_client import get_redis
from app.schemas import OIDCConfigOut, OIDCExchangeOut, OIDCExchangeRequest, TokenPair
from app.security import create_access_token, create_refresh_token

router = APIRouter(prefix="/auth/oidc", tags=["auth"])
log = get_logger(__name__)

_STATE_TYPE = "oidc_login_state"
_STATE_TTL = timedelta(minutes=10)
_EXCHANGE_PREFIX = "atlaskb:oidc_exchange"
_EXCHANGE_TTL_SECONDS = 60


def _tokens_for(user: User) -> TokenPair:
    return TokenPair(access_token=create_access_token(user.id), refresh_token=create_refresh_token(user.id))


@router.get("/config", response_model=OIDCConfigOut)
def oidc_config() -> OIDCConfigOut:
    return OIDCConfigOut(enabled=settings.oidc_enabled)


@router.get("/login")
def oidc_login() -> RedirectResponse:
    if not settings.oidc_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "SSO isn't configured on this server.")

    nonce = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    state = jwt.encode(
        {
            "type": _STATE_TYPE,
            "nonce": nonce,
            "code_verifier": code_verifier,
            "exp": int((datetime.now(UTC) + _STATE_TTL).timestamp()),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    url = authorization_url(state=state, nonce=nonce, code_verifier=code_verifier)
    return RedirectResponse(url)


@router.get("/callback")
def oidc_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != _STATE_TYPE:
            raise jwt.InvalidTokenError("wrong state token type")
    except jwt.PyJWTError:
        return RedirectResponse(f"{settings.web_base_url}/login?error=invalid_state")

    try:
        claims = exchange_code(code=code, code_verifier=payload["code_verifier"], nonce=payload["nonce"])
    except OIDCError as exc:
        log.warning("oidc.callback_failed", error=str(exc))
        return RedirectResponse(f"{settings.web_base_url}/login?error=sso_failed")

    if not claims.email_verified:
        # Refuse rather than silently create/link an account off an email
        # the IdP itself won't vouch for — auto-linking here is exactly the
        # account-takeover vector "auto-link by verified email" is supposed
        # to guard against; an unverified email must not merge into (or
        # create) a real account.
        log.warning("oidc.unverified_email", subject=claims.subject)
        return RedirectResponse(f"{settings.web_base_url}/login?error=email_not_verified")

    user = _find_or_create_user(db, claims)

    exchange_id = secrets.token_urlsafe(32)
    payload = OIDCExchangeOut(email=user.email, **_tokens_for(user).model_dump())
    get_redis().setex(f"{_EXCHANGE_PREFIX}:{exchange_id}", _EXCHANGE_TTL_SECONDS, payload.model_dump_json())
    log.info("oidc.login", user_id=user.id)
    return RedirectResponse(f"{settings.web_base_url}/login/callback?code={exchange_id}")


def _find_or_create_user(db: Session, claims: OIDCClaims) -> User:
    identity = db.scalar(
        select(UserIdentity).where(
            UserIdentity.issuer == settings.oidc_issuer, UserIdentity.subject == claims.subject
        )
    )
    if identity is not None:
        return identity.user

    # First login from this IdP subject — auto-link to an existing
    # password account with the same (IdP-verified) email if one exists,
    # else provision a brand-new, password-less account.
    user = db.scalar(select(User).where(User.email == claims.email))
    if user is None:
        user = User(email=claims.email, password_hash=None)
        db.add(user)
        db.flush()
        log.info("oidc.user_provisioned", user_id=user.id)
    else:
        log.info("oidc.user_linked", user_id=user.id)

    db.add(
        UserIdentity(
            user_id=user.id,
            provider="oidc",
            issuer=settings.oidc_issuer,
            subject=claims.subject,
            email=claims.email,
        )
    )
    db.commit()
    db.refresh(user)
    return user


@router.post("/exchange", response_model=OIDCExchangeOut)
def oidc_exchange(body: OIDCExchangeRequest) -> OIDCExchangeOut:
    key = f"{_EXCHANGE_PREFIX}:{body.code}"
    redis = get_redis()
    raw = redis.get(key)
    if raw is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This sign-in link has expired or was already used.")
    redis.delete(key)  # one-time use
    return OIDCExchangeOut(**json.loads(raw))
