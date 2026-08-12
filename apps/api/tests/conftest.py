"""Pytest fixtures.

Integration tests run against a *real* Postgres (with pgvector). A user account
is separate from a workspace: ``make_user`` signs a user up, logs them in, and
(by default) creates a workspace they administer. Workspace context is passed on
every request via the ``X-Workspace-Id`` header.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

import psycopg
import pytest

# --- Override settings BEFORE importing any app module (env > .env in pydantic). ---
_PG_HOST = os.getenv("TEST_PG_HOST", "localhost")
_PG_PORT = os.getenv("TEST_PG_PORT", "15432")
_ADMIN_DB = f"postgresql://atlaskb:atlaskb@{_PG_HOST}:{_PG_PORT}/atlaskb"
_TEST_DB_NAME = "atlaskb_test"

os.environ["DATABASE_URL"] = (
    f"postgresql+psycopg://atlaskb:atlaskb@{_PG_HOST}:{_PG_PORT}/{_TEST_DB_NAME}"
)
os.environ["EMBEDDING_BACKEND"] = "fake"
os.environ["RERANK_BACKEND"] = "fake"
os.environ["OPENROUTER_API_KEY"] = "test-key-not-used"
os.environ["JWT_SECRET"] = "test-jwt-secret-not-a-real-credential"
os.environ["REDIS_URL"] = os.getenv("TEST_REDIS_URL", f"redis://{_PG_HOST}:6380/15")
os.environ["CACHE_ENABLED"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"

from app import models  # noqa: F401  (register tables)
from app.db import Base, SessionLocal, engine
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import text

_TABLES = (
    "audit_logs",
    "conflicts",
    "connector_documents",
    "connector_configs",
    "message_feedback",
    "messages",
    "conversations",
    "chunks",
    "document_versions",
    "document_access_grants",
    "documents",
    "api_keys",
    "invites",
    "workspace_memberships",
    "workspaces",
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
    token: str
    workspace_id: str | None = None  # the workspace this user created (admin of)

    @property
    def bearer(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    @property
    def headers(self) -> dict[str, str]:
        """Auth + this user's own workspace."""
        h = dict(self.bearer)
        if self.workspace_id:
            h["X-Workspace-Id"] = self.workspace_id
        return h

    def in_ws(self, workspace_id: str) -> dict[str, str]:
        """Auth headers scoped to an arbitrary workspace the user belongs to."""
        return {**self.bearer, "X-Workspace-Id": workspace_id}


@pytest.fixture
def make_user(client):
    """Factory: sign up + log in a user, optionally creating a workspace they admin."""

    def _make(email: str | None = None, create_workspace: bool = True, workspace_name: str = "WS") -> UserCtx:
        email = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
        password = "supersecret123"
        signup = client.post("/auth/signup", json={"email": email, "password": password})
        assert signup.status_code == 201, signup.text
        user_id = signup.json()["id"]
        token = client.post(
            "/auth/login", json={"email": email, "password": password}
        ).json()["access_token"]
        ctx = UserCtx(email=email, password=password, user_id=user_id, token=token)
        if create_workspace:
            ws = client.post(
                "/workspaces", headers=ctx.bearer, json={"name": workspace_name}
            )
            assert ws.status_code == 201, ws.text
            ctx.workspace_id = ws.json()["id"]
        return ctx

    return _make


@pytest.fixture
def grant_membership():
    """Add a user to a workspace with a role directly (fast test setup)."""

    def _grant(user_id: str, workspace_id: str, role: str) -> None:
        from app.models import WorkspaceMembership

        s = SessionLocal()
        try:
            s.add(WorkspaceMembership(workspace_id=workspace_id, user_id=user_id, role=role))
            s.commit()
        finally:
            s.close()

    return _grant


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
    """Deterministic offline LLM: context sufficient; answer cites chunk #1."""
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
