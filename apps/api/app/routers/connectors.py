"""Connector management + Google Drive OAuth (Trust Layer Phase 11).

Every endpoint except the OAuth callback is workspace-scoped and
admin-only, mirroring every other admin router in this codebase
(``Depends(require_role(ROLE_ADMIN))``). The callback is the one
exception: Google's server redirects the admin's browser there with only
``code``/``state`` query params, no Authorization header — the short-lived
signed ``state`` JWT minted by the authorize endpoint is what carries
workspace/user/name/folder context across that unauthenticated hop.
"""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.celery_client import enqueue_connector_sync
from app.config import settings
from app.connectors import ConnectorError, connector_from_config
from app.connectors.tokens import encrypt_credentials
from app.db import get_db
from app.deps import require_role
from app.logging_config import get_logger
from app.models import ROLE_ADMIN, ConnectorConfig
from app.rbac import Principal
from app.schemas import ConnectorAuthorizeOut, ConnectorCreate, ConnectorOut

router = APIRouter(prefix="/connectors", tags=["connectors"])
log = get_logger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
_STATE_TYPE = "connector_oauth_state"
_STATE_TTL = timedelta(minutes=15)
_FOLDER_URL_RE = re.compile(r"/folders/([a-zA-Z0-9_-]+)")


def _normalize_folder_id(raw: str | None) -> str | None:
    """Admins naturally paste the whole folder URL from their browser's
    address bar (``.../drive/folders/<id>?usp=sharing``), not the bare id
    the Drive API actually wants — passing the full URL straight through
    as a file id makes every ``files.list`` call 404. Extract the id out of
    a URL if one was pasted; otherwise assume it's already a bare id."""
    if not raw:
        return None
    raw = raw.strip()
    match = _FOLDER_URL_RE.search(raw)
    return match.group(1) if match else raw


def _require_google_config() -> None:
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Google Drive isn't configured on this server — GOOGLE_CLIENT_ID/"
            "GOOGLE_CLIENT_SECRET are unset. See .env.example.",
        )


def _flow(*, code_verifier: str | None = None) -> Flow:
    """``code_verifier`` matters across the authorize/callback split: Google's
    PKCE flow generates one when building the authorize URL and needs the
    *same* one back when exchanging the code, but authorize and callback are
    two separate requests (and, with a reloading dev server, sometimes two
    separate processes) — a fresh ``Flow`` object here has no memory of the
    other request's verifier. The caller round-trips it through the signed
    ``state`` token instead, the same way it already carries name/folder_id."""
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.google_redirect_uri],
            }
        },
        scopes=_SCOPES,
        redirect_uri=settings.google_redirect_uri,
        code_verifier=code_verifier,
    )


def _get_owned_connector(db: Session, principal: Principal, connector_id: str) -> ConnectorConfig:
    config = db.get(ConnectorConfig, connector_id)
    # Never confirm existence of a connector outside the caller's workspace.
    if config is None or config.workspace_id != principal.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector not found")
    return config


@router.get("", response_model=list[ConnectorOut])
def list_connectors(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role(ROLE_ADMIN)),
) -> list[ConnectorOut]:
    rows = db.scalars(
        select(ConnectorConfig)
        .where(ConnectorConfig.workspace_id == principal.workspace_id)
        .order_by(ConnectorConfig.created_at.desc())
    ).all()
    return [
        ConnectorOut(
            id=r.id,
            provider=r.provider,
            name=r.name,
            status=r.status,
            connected=r.credentials_ref is not None,
            created_at=r.created_at,
            last_sync_at=r.last_sync_at,
            last_sync_status=r.last_sync_status,
        )
        for r in rows
    ]


@router.post("/google/authorize", response_model=ConnectorAuthorizeOut)
def authorize_google_drive(
    body: ConnectorCreate,
    principal: Principal = Depends(require_role(ROLE_ADMIN)),
) -> ConnectorAuthorizeOut:
    """Starts the OAuth flow. No ``ConnectorConfig`` row exists yet — it's
    only created by the callback below once a real refresh token comes
    back, so an admin abandoning Google's consent screen leaves nothing
    half-configured behind."""
    _require_google_config()
    # Generated up front (rather than letting authorization_url() autogenerate
    # one) so it can be embedded in `state` before the URL is built — the
    # callback's separately-constructed Flow object needs this exact same
    # verifier to exchange the code, and has no other way to get it.
    code_verifier = secrets.token_urlsafe(64)[:128]
    state = jwt.encode(
        {
            "type": _STATE_TYPE,
            "workspace_id": principal.workspace_id,
            "user_id": principal.user_id,
            "name": body.name,
            "folder_id": _normalize_folder_id(body.folder_id),
            "code_verifier": code_verifier,
            "exp": int((datetime.now(UTC) + _STATE_TTL).timestamp()),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    authorize_url, _ = _flow(code_verifier=code_verifier).authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
        state=state,
    )
    return ConnectorAuthorizeOut(authorize_url=authorize_url)


@router.get("/google/callback")
def google_drive_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != _STATE_TYPE:
            raise jwt.InvalidTokenError("wrong state token type")
    except jwt.PyJWTError:
        return RedirectResponse(f"{settings.web_base_url}/admin/connectors?error=invalid_state")

    try:
        flow = _flow(code_verifier=payload.get("code_verifier"))
        flow.fetch_token(code=code)
        refresh_token = flow.credentials.refresh_token
    except Exception as exc:  # noqa: BLE001 - surfaced as a redirect error, never a 500 to the browser
        log.warning("connector.google_oauth_exchange_failed", error=str(exc))
        return RedirectResponse(f"{settings.web_base_url}/admin/connectors?error=token_exchange_failed")

    if not refresh_token:
        # Google omits refresh_token when this account already granted the
        # app consent before and it decides not to re-issue one.
        # access_type=offline + prompt=consent above are exactly what avoid
        # this in the normal case, but a stale prior grant can still hit it
        # — the fix is revoking access at myaccount.google.com/permissions
        # and reconnecting.
        return RedirectResponse(f"{settings.web_base_url}/admin/connectors?error=no_refresh_token")

    credentials_ref = encrypt_credentials(
        {"refresh_token": refresh_token, "folder_id": payload.get("folder_id")}
    )
    config = ConnectorConfig(
        workspace_id=payload["workspace_id"],
        provider="google_drive",
        name=payload["name"],
        credentials_ref=credentials_ref,
        status="active",
        created_by=payload["user_id"],
    )
    db.add(config)
    db.commit()
    log.info("connector.google_drive_connected", workspace_id=payload["workspace_id"], connector_id=config.id)
    return RedirectResponse(f"{settings.web_base_url}/admin/connectors?connected={config.id}")


@router.post("/{connector_id}/sync", status_code=status.HTTP_202_ACCEPTED)
def sync_now(
    connector_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role(ROLE_ADMIN)),
) -> dict:
    config = _get_owned_connector(db, principal, connector_id)
    if config.credentials_ref is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Connector isn't connected yet.")
    enqueue_connector_sync(config.id, principal.user_id)
    return {"queued": True}


@router.post("/{connector_id}/test")
def test_connection(
    connector_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role(ROLE_ADMIN)),
) -> dict:
    """Cheap reachability check for the admin UI's "Test connection"
    button — authenticates and pings Drive, never runs a real sync (no
    ingestion side effects)."""
    config = _get_owned_connector(db, principal, connector_id)
    if config.credentials_ref is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Connector isn't connected yet.")
    try:
        connector = connector_from_config(config)
        connector.authenticate()
        ok = connector.test_connection()
    except ConnectorError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": ok}


@router.delete("/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connector(
    connector_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role(ROLE_ADMIN)),
) -> None:
    """Removes the connector config (and, via the DB's ON DELETE CASCADE,
    its ``ConnectorDocument`` sync-state rows). The ``Document`` rows it
    already created stay — disconnecting a source stops the feed, it
    doesn't retroactively delete what was already ingested."""
    config = _get_owned_connector(db, principal, connector_id)
    db.delete(config)
    db.commit()
