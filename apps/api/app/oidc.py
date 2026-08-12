"""Generic OIDC client (Trust Layer Phase 11: SSO).

Works against any standards-compliant OIDC provider (Google Workspace,
Okta, Azure AD, ...) driven entirely by ``settings.oidc_issuer`` — no
provider-specific code, unlike the Google Drive connector (which talks to
one concrete API, not a generic protocol). The provider is discovered via
its ``/.well-known/openid-configuration`` document, and the OAuth2
authorization-code + PKCE flow is built with ``requests_oauthlib`` (already
an installed transitive dependency of ``google-auth-oauthlib`` — no new
package needed). ID token signature verification uses ``jwt.PyJWKClient``,
built into PyJWT since 2.x — also no new dependency.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from functools import lru_cache

import jwt
import requests
from requests_oauthlib import OAuth2Session

from app.config import settings


class OIDCError(Exception):
    """Raised on any failure talking to the IdP or validating its response —
    callers must treat this as "the SSO attempt failed," not retry blindly."""


@dataclass
class OIDCClaims:
    subject: str
    email: str
    email_verified: bool
    name: str | None


def _require_configured() -> None:
    if not settings.oidc_enabled:
        raise OIDCError(
            "OIDC SSO isn't configured on this server — OIDC_ISSUER/OIDC_CLIENT_ID/"
            "OIDC_CLIENT_SECRET are unset. See .env.example."
        )


@lru_cache(maxsize=8)
def _discovery_document(issuer: str) -> dict:
    """Cached per issuer for the process lifetime — the discovery document
    is effectively static (rotating it requires a coordinated IdP-side
    migration), so re-fetching it on every login would just be a slow,
    pointless network round trip on the auth hot path."""
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise OIDCError(f"Couldn't reach the OIDC discovery document at {url}: {exc}") from exc


@lru_cache(maxsize=8)
def _jwks_client(jwks_uri: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_uri)


def authorization_url(*, state: str, nonce: str, code_verifier: str) -> str:
    _require_configured()
    doc = _discovery_document(settings.oidc_issuer)
    session = OAuth2Session(
        client_id=settings.oidc_client_id,
        redirect_uri=settings.oidc_redirect_uri,
        scope=["openid", "email", "profile"],
    )
    code_challenge = _pkce_challenge(code_verifier)
    url, _ = session.authorization_url(
        doc["authorization_endpoint"],
        state=state,
        nonce=nonce,
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )
    return url


def _pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def exchange_code(*, code: str, code_verifier: str, nonce: str) -> OIDCClaims:
    """Exchanges an authorization code for tokens, then verifies the ID
    token's signature (against the IdP's live JWKS) and standard claims
    (issuer, audience, expiry, nonce) before trusting anything in it."""
    _require_configured()
    doc = _discovery_document(settings.oidc_issuer)
    session = OAuth2Session(client_id=settings.oidc_client_id, redirect_uri=settings.oidc_redirect_uri)
    try:
        token = session.fetch_token(
            doc["token_endpoint"],
            code=code,
            client_secret=settings.oidc_client_secret,
            code_verifier=code_verifier,
        )
    except Exception as exc:
        raise OIDCError(f"OIDC code exchange failed: {exc}") from exc

    id_token = token.get("id_token")
    if not id_token:
        raise OIDCError("The IdP didn't return an id_token — check that the 'openid' scope was granted.")

    return _verify_id_token(id_token, doc["jwks_uri"], nonce=nonce)


def _verify_id_token(id_token: str, jwks_uri: str, *, nonce: str) -> OIDCClaims:
    client = _jwks_client(jwks_uri)
    try:
        signing_key = client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.oidc_client_id,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise OIDCError(f"ID token verification failed: {exc}") from exc

    # PyJWT validates the registered claims (iss/aud/exp/...) but has no
    # concept of `nonce` — it's an OIDC-specific replay-protection claim we
    # must check ourselves against the value minted at authorize time.
    if claims.get("nonce") != nonce:
        raise OIDCError("ID token nonce mismatch — possible replay or CSRF attempt.")

    email = claims.get("email")
    if not email:
        raise OIDCError("The IdP didn't include an email claim — request the 'email' scope.")

    return OIDCClaims(
        subject=claims["sub"],
        email=email,
        email_verified=bool(claims.get("email_verified", False)),
        name=claims.get("name"),
    )
