"""Pytest fixtures.

Integration tests run against a *real* Postgres (with pgvector) so the dense +
full-text SQL is exercised for real — only the embedding backend is swapped for
the deterministic ``fake`` one. The semantic cache and rate limiter are disabled
by default (the tests that exercise them opt in) and use a dedicated Redis DB.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

import psycopg
import pytest

# --- Override settings BEFORE importing any app module (env > .env in pydantic). ---
# Local test DB connection is assembled from parts (no credential literal in
# source); override via POSTGRES_USER/POSTGRES_PASSWORD or TEST_PG_* if needed.
_PG_HOST = os.getenv("TEST_PG_HOST", "localhost")
_PG_PORT = os.getenv("TEST_PG_PORT", "15432")
_PG_USER = os.getenv("POSTGRES_USER", "atlaskb")
_PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "atlaskb")
_TEST_DB_NAME = "atlaskb_test"
_CREDS = f"{_PG_USER}:{_PG_PASSWORD}@{_PG_HOST}:{_PG_PORT}"
_ADMIN_DB = f"postgresql://{_CREDS}/atlaskb"

os.environ["DATABASE_URL"] = f"postgresql+psycopg://{_CREDS}/{_TEST_DB_NAME}"
os.environ["EMBEDDING_BACKEND"] = "fake"
os.environ["OPENROUTER_API_KEY"] = "test-key-not-used"
os.environ["JWT_SECRET"] = "test-jwt-secret-not-a-real-credential"
# Dedicated Redis DB so cache/rate-limit tests never touch app data.
os.environ["REDIS_URL"] = os.getenv("TEST_REDIS_URL", f"redis://{_PG_HOST}:6380/15")
# Off by default; the cache/rate-limit tests enable them explicitly.
os.environ["CACHE_ENABLED"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"

from app import models  # noqa: F401  (register tables)
from app.db import Base, SessionLocal, engine
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import text

_TABLES = (
    "messages",
    "conversations",
    "chunks",
    "document_acls",
    "documents",
    "api_keys",
    "tenant_memberships",
    "tenants",
    "users",
)


def _recreate_test_database() -> None:
    with psycopg.connect(_ADMIN_DB, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{_TEST_DB_NAME}"')


@pytest.fixture(scope="session", autouse=True)
def _database():
    _recreate_test_database()
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_state(_database):
    """Truncate all tables and flush the test Redis DB between tests."""
    yield
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE"))
    try:
        from app.redis_client import get_redis

        get_redis().flushdb()
    except Exception:  # noqa: BLE001,S110 - Redis only needed for cache/RL tests
        pass


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    return TestClient(app)


@dataclass
class UserCtx:
    email: str
    password: str
    user_id: str
    tenant_id: str  # personal workspace
    headers: dict[str, str]


@pytest.fixture
def make_user(client):
    """Factory: sign up + log in a fresh user, returning their context."""

    def _make(email: str | None = None, password: str = "supersecret123") -> UserCtx:
        email = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
        signup = client.post("/auth/signup", json={"email": email, "password": password})
        assert signup.status_code == 201, signup.text
        user_id = signup.json()["id"]
        tokens = client.post(
            "/auth/login", json={"email": email, "password": password}
        ).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        workspaces = client.get("/workspaces", headers=headers).json()
        tenant_id = workspaces[0]["id"]
        return UserCtx(
            email=email,
            password=password,
            user_id=user_id,
            tenant_id=tenant_id,
            headers=headers,
        )

    return _make


@pytest.fixture
def auth_headers(make_user):
    return make_user().headers


@pytest.fixture
def ingest_inline(monkeypatch):
    """Run ingestion synchronously on upload instead of via Celery."""
    from app.ingest import ingest_document

    monkeypatch.setattr(
        "app.routers.documents.enqueue_ingest", lambda doc_id: ingest_document(doc_id)
    )


@pytest.fixture
def stub_llm(monkeypatch):
    """Deterministic LLM: context is always sufficient; answer cites chunk #1.

    Avoids any network call so /chat is deterministic and offline.
    """
    from app.llm import CANNOT_ANSWER, Assessment, GroundedAnswer

    def fake_assess(question, chunks):
        return Assessment(sufficient=True, refined_query=None)

    def fake_generate(question, chunks):
        if not chunks:
            return GroundedAnswer(False, CANNOT_ANSWER, [])
        return GroundedAnswer(
            True,
            f"Grounded answer about: {chunks[0].text[:40]}",
            [{"claim": "supported", "chunk_ids": [chunks[0].chunk_id]}],
        )

    monkeypatch.setattr("app.llm.assess_context", fake_assess)
    monkeypatch.setattr("app.llm.generate_answer", fake_generate)
