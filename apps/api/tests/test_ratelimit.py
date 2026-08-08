"""Per-user and per-tenant rate limiting (Redis fixed window)."""

from __future__ import annotations

import pytest
from app.config import settings


@pytest.fixture
def rate_limit_on(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)


def test_per_user_limit_returns_429(client, make_user, rate_limit_on, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_user_per_min", 3)
    monkeypatch.setattr(settings, "rate_limit_tenant_per_min", 1000)
    user = make_user()

    for _ in range(3):
        assert client.post("/search", headers=user.headers, json={"query": "x"}).status_code == 200
    r = client.post("/search", headers=user.headers, json={"query": "x"})
    assert r.status_code == 429
    assert "Retry-After" in r.headers


def test_per_tenant_limit_counts_all_members(
    client, make_user, grant_membership, rate_limit_on, monkeypatch
):
    monkeypatch.setattr(settings, "rate_limit_user_per_min", 1000)
    monkeypatch.setattr(settings, "rate_limit_tenant_per_min", 3)

    admin = make_user()
    member = make_user(create_workspace=False)
    grant_membership(member.user_id, admin.workspace_id, "viewer")
    member_hdr = member.in_ws(admin.workspace_id)

    # Two requests from admin + one from member = 3 (the tenant limit).
    assert client.post("/search", headers=admin.headers, json={"query": "x"}).status_code == 200
    assert client.post("/search", headers=admin.headers, json={"query": "x"}).status_code == 200
    assert client.post("/search", headers=member_hdr, json={"query": "x"}).status_code == 200
    # The 4th request in the tenant window is rejected regardless of who sends it.
    assert client.post("/search", headers=member_hdr, json={"query": "x"}).status_code == 429


def test_disabled_by_default(client, make_user):
    user = make_user()
    # No rate_limit_on fixture → limiter is off; many calls all succeed.
    for _ in range(8):
        assert client.post("/search", headers=user.headers, json={"query": "x"}).status_code == 200
