"""Admin analytics + evals endpoints, and chat token-usage reporting."""

from __future__ import annotations

import io
import json

from app.config import settings


def _upload(client, headers, body=b"# Doc\n\nMars is the Red Planet.\n"):
    return client.post(
        "/documents", headers=headers, files={"file": ("d.md", io.BytesIO(body), "text/markdown")}
    )


def test_analytics_reports_real_tenant_counts(client, make_user, ingest_inline, stub_llm):
    user = make_user()
    _upload(client, user.headers)
    client.post("/chat", headers=user.headers, json={"question": "What is Mars?"})

    r = client.get("/admin/analytics", headers=user.headers)
    assert r.status_code == 200
    data = r.json()
    assert data["documents_total"] == 1
    assert data["documents_by_status"].get("ready") == 1
    assert data["chunks_total"] >= 1
    assert data["conversations_total"] == 1
    assert data["messages_total"] == 2  # user + assistant
    assert data["members_total"] == 1
    assert sum(d["count"] for d in data["questions_last_7_days"]) == 1


def test_analytics_requires_admin(client, make_user):
    admin = make_user()
    viewer = make_user()
    client.post(
        f"/workspaces/{admin.tenant_id}/invite",
        headers=admin.headers,
        json={"email": viewer.email, "role": "viewer"},
    )
    r = client.get(
        "/admin/analytics", headers={**viewer.headers, "X-Tenant-Id": admin.tenant_id}
    )
    assert r.status_code == 403


def test_evals_available_flag(client, make_user, tmp_path, monkeypatch):
    user = make_user()

    monkeypatch.setattr(settings, "eval_results_path", str(tmp_path / "missing.json"))
    assert client.get("/admin/evals", headers=user.headers).json()["available"] is False

    results = {"metrics": {"answer_accuracy": 1.0}, "model": "test"}
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(results))
    monkeypatch.setattr(settings, "eval_results_path", str(path))
    body = client.get("/admin/evals", headers=user.headers).json()
    assert body["available"] is True
    assert body["metrics"]["answer_accuracy"] == 1.0


def test_chat_response_includes_usage(client, make_user, ingest_inline, stub_llm):
    user = make_user()
    _upload(client, user.headers)
    r = client.post("/chat", headers=user.headers, json={"question": "What is Mars?"})
    assert r.status_code == 200
    assert "usage" in r.json()
    assert set(r.json()["usage"]) == {"prompt", "completion", "total"}
