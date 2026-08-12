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


def test_analytics_requires_admin(client, make_user, grant_membership):
    admin = make_user()
    viewer = make_user(create_workspace=False)
    grant_membership(viewer.user_id, admin.workspace_id, "viewer")
    r = client.get("/admin/analytics", headers=viewer.in_ws(admin.workspace_id))
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


def test_evals_headline_assembled_from_real_files(client, make_user, tmp_path, monkeypatch):
    """T9.8: the headline block must be built from eval/results/*.json files
    found on disk, not hand-typed — plant a fake results dir and confirm every
    field traces back to the file that provided it."""
    user = make_user()

    path = tmp_path / "latest.json"
    path.write_text(json.dumps({"metrics": {}, "model": "test"}))
    monkeypatch.setattr(settings, "eval_results_path", str(path))

    (tmp_path / "before_after_after.json").write_text(json.dumps({
        "dataset_size": 17,
        "metrics": {
            "answer_accuracy": 0.929,
            "retrieval_hit_rate": 1.0,
            "citation_grounding": 0.857,
            "citation_coverage": 0.75,
            "conflict_detection_accuracy": 0.25,
            "refusal_accuracy": 1.0,
        },
        "permission_leakage_detail": {"pass": True},
    }))
    (tmp_path / "adversarial.json").write_text(json.dumps({"passed": 6, "total": 7}))
    (tmp_path / "prompt_injection.json").write_text(json.dumps({"passed": 3, "total": 3}))
    (tmp_path / "latency_breakdown_ollama_steady_state.json").write_text(json.dumps({
        "total": {"mean_ms": 8397.7, "p95_ms": 10590.7},
    }))

    body = client.get("/admin/evals", headers=user.headers).json()
    h = body["headline"]
    assert h["total_questions"] == 17
    assert h["answer_accuracy"] == 0.929
    assert h["citation_coverage"] == 0.75
    assert h["permission_leakage"] == 0
    assert h["adversarial_passed"] == 6 and h["adversarial_total"] == 7
    assert h["prompt_injection_passed"] == 3 and h["prompt_injection_total"] == 3
    assert h["avg_latency_ms"] == 8397.7
    assert h["p95_latency_ms"] == 10590.7
    assert "before_after_after.json" in h["source_files"]
    assert "load-latest.json" in h["missing_files"]


def test_evals_headline_permission_leakage_none_when_unmeasured(client, make_user, tmp_path, monkeypatch):
    user = make_user()
    path = tmp_path / "latest.json"
    path.write_text(json.dumps({"metrics": {}, "model": "test"}))
    monkeypatch.setattr(settings, "eval_results_path", str(path))

    body = client.get("/admin/evals", headers=user.headers).json()
    # No before_after_after.json planted at all -> genuinely unmeasured, must
    # be None, never silently 0 (0 would falsely read as "measured and clean").
    assert body["headline"]["permission_leakage"] is None


def test_chat_response_includes_usage(client, make_user, ingest_inline, stub_llm):
    user = make_user()
    _upload(client, user.headers)
    r = client.post("/chat", headers=user.headers, json={"question": "What is Mars?"})
    assert r.status_code == 200
    assert "usage" in r.json()
    assert set(r.json()["usage"]) == {"prompt", "completion", "total"}
