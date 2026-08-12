"""SSO / OIDC (Trust Layer Phase 11).

No real IdP is exercised here (that needs a real OIDC app registration —
same rule the connector tests follow, see tests/test_connectors.py). What
*is* tested without any network: ID token signature/claims verification
against a locally-generated RSA keypair standing in for an IdP's JWKS, and
the find-or-create/auto-link-by-verified-email logic against the real DB —
both are pure logic this codebase owns and can fully exercise on its own.
"""

from __future__ import annotations

import time

import jwt as pyjwt
import pytest
from app.db import SessionLocal
from app.models import User, UserIdentity
from app.oidc import OIDCClaims, OIDCError, _verify_id_token
from app.routers.oidc import _find_or_create_user
from cryptography.hazmat.primitives.asymmetric import rsa

_ISSUER = "https://idp.example.com"
_AUDIENCE = "test-client-id"


@pytest.fixture
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _make_id_token(private_key, *, kid="test-kid", **claim_overrides):
    now = int(time.time())
    claims = {
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "sub": "idp-subject-1",
        "email": "person@example.com",
        "email_verified": True,
        "iat": now,
        "exp": now + 300,
        "nonce": "expected-nonce",
    }
    claims.update(claim_overrides)
    return pyjwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKSClient:
    def __init__(self, public_key):
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(self._public_key)


def test_verify_id_token_accepts_valid_token(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    monkeypatch.setattr("app.oidc.settings.oidc_issuer", _ISSUER)
    monkeypatch.setattr("app.oidc.settings.oidc_client_id", _AUDIENCE)
    monkeypatch.setattr("app.oidc._jwks_client", lambda uri: _FakeJWKSClient(public_key))

    token = _make_id_token(private_key)
    claims = _verify_id_token(token, "https://idp.example.com/jwks", nonce="expected-nonce")

    assert claims.subject == "idp-subject-1"
    assert claims.email == "person@example.com"
    assert claims.email_verified is True


def test_verify_id_token_rejects_nonce_mismatch(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    monkeypatch.setattr("app.oidc.settings.oidc_issuer", _ISSUER)
    monkeypatch.setattr("app.oidc.settings.oidc_client_id", _AUDIENCE)
    monkeypatch.setattr("app.oidc._jwks_client", lambda uri: _FakeJWKSClient(public_key))

    token = _make_id_token(private_key)
    with pytest.raises(OIDCError, match="nonce"):
        _verify_id_token(token, "https://idp.example.com/jwks", nonce="a-different-nonce")


def test_verify_id_token_rejects_wrong_audience(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    monkeypatch.setattr("app.oidc.settings.oidc_issuer", _ISSUER)
    monkeypatch.setattr("app.oidc.settings.oidc_client_id", _AUDIENCE)
    monkeypatch.setattr("app.oidc._jwks_client", lambda uri: _FakeJWKSClient(public_key))

    token = _make_id_token(private_key, aud="someone-elses-client-id")
    with pytest.raises(OIDCError, match="verification failed"):
        _verify_id_token(token, "https://idp.example.com/jwks", nonce="expected-nonce")


def test_verify_id_token_rejects_expired_token(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    monkeypatch.setattr("app.oidc.settings.oidc_issuer", _ISSUER)
    monkeypatch.setattr("app.oidc.settings.oidc_client_id", _AUDIENCE)
    monkeypatch.setattr("app.oidc._jwks_client", lambda uri: _FakeJWKSClient(public_key))

    now = int(time.time())
    token = _make_id_token(private_key, iat=now - 1000, exp=now - 500)
    with pytest.raises(OIDCError, match="verification failed"):
        _verify_id_token(token, "https://idp.example.com/jwks", nonce="expected-nonce")


def test_verify_id_token_rejects_missing_email(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    monkeypatch.setattr("app.oidc.settings.oidc_issuer", _ISSUER)
    monkeypatch.setattr("app.oidc.settings.oidc_client_id", _AUDIENCE)
    monkeypatch.setattr("app.oidc._jwks_client", lambda uri: _FakeJWKSClient(public_key))

    token = _make_id_token(private_key, email="")
    with pytest.raises(OIDCError, match="email"):
        _verify_id_token(token, "https://idp.example.com/jwks", nonce="expected-nonce")


def test_find_or_create_provisions_new_sso_only_user(monkeypatch):
    monkeypatch.setattr("app.routers.oidc.settings.oidc_issuer", _ISSUER)
    db = SessionLocal()
    try:
        claims = OIDCClaims(subject="sub-new", email="brand-new@example.com", email_verified=True, name="New")
        user = _find_or_create_user(db, claims)
        assert user.email == "brand-new@example.com"
        assert user.password_hash is None

        identity = db.query(UserIdentity).filter_by(subject="sub-new").one()
        assert identity.user_id == user.id
        assert identity.issuer == _ISSUER
    finally:
        db.query(UserIdentity).filter_by(subject="sub-new").delete()
        db.query(User).filter_by(email="brand-new@example.com").delete()
        db.commit()
        db.close()


def test_find_or_create_auto_links_existing_password_account_by_verified_email(monkeypatch, make_user):
    monkeypatch.setattr("app.routers.oidc.settings.oidc_issuer", _ISSUER)
    existing = make_user()
    db = SessionLocal()
    try:
        claims = OIDCClaims(subject="sub-link", email=existing.email, email_verified=True, name=None)
        user = _find_or_create_user(db, claims)

        assert user.id == existing.user_id
        assert user.password_hash is not None  # unchanged -- still logs in with a password too

        identity = db.query(UserIdentity).filter_by(subject="sub-link").one()
        assert identity.user_id == existing.user_id
    finally:
        db.query(UserIdentity).filter_by(subject="sub-link").delete()
        db.commit()
        db.close()


def test_find_or_create_returns_same_user_on_repeat_login(monkeypatch):
    monkeypatch.setattr("app.routers.oidc.settings.oidc_issuer", _ISSUER)
    db = SessionLocal()
    try:
        claims = OIDCClaims(subject="sub-repeat", email="repeat@example.com", email_verified=True, name=None)
        first = _find_or_create_user(db, claims)
        second = _find_or_create_user(db, claims)
        assert first.id == second.id
        assert db.query(UserIdentity).filter_by(subject="sub-repeat").count() == 1
    finally:
        db.query(UserIdentity).filter_by(subject="sub-repeat").delete()
        db.query(User).filter_by(email="repeat@example.com").delete()
        db.commit()
        db.close()


def test_password_login_rejects_sso_only_account(client):
    db = SessionLocal()
    try:
        user = User(email="sso-only@example.com", password_hash=None)
        db.add(user)
        db.commit()
    finally:
        db.close()

    r = client.post("/auth/login", json={"email": "sso-only@example.com", "password": "whatever123"})
    assert r.status_code == 401

    db = SessionLocal()
    try:
        db.query(User).filter_by(email="sso-only@example.com").delete()
        db.commit()
    finally:
        db.close()


def test_oidc_config_reports_disabled_when_unconfigured(client, monkeypatch):
    # Forced explicitly rather than relying on ambient .env state -- local
    # dev's .env may have real OIDC_* values set for live-testing SSO
    # against a real IdP, which must not make this test environment-dependent.
    monkeypatch.setattr("app.routers.oidc.settings.oidc_issuer", "")
    r = client.get("/auth/oidc/config")
    assert r.status_code == 200
    assert r.json() == {"enabled": False}


def test_oidc_login_503_when_unconfigured(client, monkeypatch):
    monkeypatch.setattr("app.routers.oidc.settings.oidc_issuer", "")
    r = client.get("/auth/oidc/login", follow_redirects=False)
    assert r.status_code == 503


def test_oidc_exchange_rejects_unknown_code(client):
    r = client.post("/auth/oidc/exchange", json={"code": "not-a-real-code"})
    assert r.status_code == 400
