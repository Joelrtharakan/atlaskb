"""Content-gap cause classification (Trust Layer Phase 7)."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

from app.content_gaps import GapCause, compute_gaps
from app.db import SessionLocal
from app.llm import CANNOT_ANSWER
from app.models import Conversation, Message


def _seed_unanswered(workspace_id: str, user_id: str, question: str, *, occurrences: int = 1) -> None:
    s = SessionLocal()
    try:
        base = datetime.now(UTC)
        for i in range(occurrences):
            convo = Conversation(workspace_id=workspace_id, user_id=user_id, title=question[:50])
            s.add(convo)
            s.flush()
            s.add(
                Message(
                    conversation_id=convo.id, workspace_id=workspace_id, role="user",
                    content=question, created_at=base + timedelta(seconds=i * 2),
                )
            )
            s.add(
                Message(
                    conversation_id=convo.id, workspace_id=workspace_id, role="assistant",
                    content=CANNOT_ANSWER, created_at=base + timedelta(seconds=i * 2 + 1),
                )
            )
        s.commit()
    finally:
        s.close()


def _upload(client, headers, body: bytes, filename: str = "d.md"):
    r = client.post("/documents", headers=headers, files={"file": (filename, io.BytesIO(body), "text/markdown")})
    r.raise_for_status()
    return r.json()


def test_no_document_at_all_classifies_missing_document(client, make_user):
    admin = make_user()
    _seed_unanswered(admin.workspace_id, admin.user_id, "What is the refund policy for annual plans?")
    db = SessionLocal()
    try:
        gaps = compute_gaps(db, admin.workspace_id, resolved_keys=set())
    finally:
        db.close()
    assert len(gaps) == 1
    assert gaps[0].cause == GapCause.MISSING_DOCUMENT.value
    assert gaps[0].relevant_document_ids == []


def test_short_question_classifies_ambiguous(client, make_user):
    admin = make_user()
    _seed_unanswered(admin.workspace_id, admin.user_id, "the policy?")
    db = SessionLocal()
    try:
        gaps = compute_gaps(db, admin.workspace_id, resolved_keys=set())
    finally:
        db.close()
    assert gaps[0].cause == GapCause.AMBIGUOUS_QUERY.value


def test_stale_document_classifies_outdated(client, make_user, ingest_inline):
    admin = make_user()
    doc = _upload(
        client, admin.headers,
        b"# Retention Policy\n\nData retention follows a fixed schedule for compliance purposes.\n",
    )
    db = SessionLocal()
    try:
        from app.models import Document

        d = db.get(Document, doc["id"])
        d.created_at = datetime.now(UTC) - timedelta(days=200)
        db.commit()
    finally:
        db.close()

    _seed_unanswered(admin.workspace_id, admin.user_id, "What is the data retention schedule for compliance?")
    db = SessionLocal()
    try:
        gaps = compute_gaps(db, admin.workspace_id, resolved_keys=set())
    finally:
        db.close()
    assert gaps[0].cause == GapCause.OUTDATED_DOCUMENT.value
    assert doc["id"] in gaps[0].relevant_document_ids


def test_restricted_document_classifies_permission_restriction(
    client, make_user, grant_membership, ingest_inline
):
    admin = make_user()
    viewer = make_user(create_workspace=False)
    grant_membership(viewer.user_id, admin.workspace_id, "viewer")

    doc = _upload(
        client, admin.headers,
        b"# Executive Severance Terms\n\nSeverance for executives follows a distinct schedule from standard staff.\n",
    )
    client.patch(
        f"/documents/{doc['id']}/access", headers=admin.headers,
        json={"grants": [{"grant_type": "role", "role_or_user_id": "admin"}]},
    )

    _seed_unanswered(admin.workspace_id, viewer.user_id, "What is the executive severance schedule?")
    db = SessionLocal()
    try:
        gaps = compute_gaps(db, admin.workspace_id, resolved_keys=set())
    finally:
        db.close()
    assert gaps[0].cause == GapCause.PERMISSION_RESTRICTION.value
    assert viewer.user_id in gaps[0].affected_user_ids


def test_conflicting_sources_classify_conflicting_document(client, make_user, ingest_inline):
    """Uses the real deterministic (no-LLM) conflict path directly — this is
    also the perf fix: classification must never make an LLM call, since it
    runs on every admin page load (a live run against a workspace with real
    history was measured taking 60-85s before this fix)."""
    admin = make_user()
    _upload(
        client, admin.headers,
        b"# HR PTO Policy\n\nEmployees receive 20 days of annual leave per year.\n",
        "hr.md",
    )
    _upload(
        client, admin.headers,
        b"# Engineering PTO Policy\n\nEmployees receive 25 days of annual leave per year.\n",
        "eng.md",
    )
    _seed_unanswered(admin.workspace_id, admin.user_id, "How many days of annual leave do employees get?")
    db = SessionLocal()
    try:
        gaps = compute_gaps(db, admin.workspace_id, resolved_keys=set())
    finally:
        db.close()
    assert gaps[0].cause == GapCause.CONFLICTING_DOCUMENT.value
    assert len(gaps[0].relevant_document_ids) == 2


def test_classify_false_skips_classification(client, make_user):
    admin = make_user()
    _seed_unanswered(admin.workspace_id, admin.user_id, "What is the refund policy for annual plans?")
    db = SessionLocal()
    try:
        gaps = compute_gaps(db, admin.workspace_id, resolved_keys=set(), classify=False)
    finally:
        db.close()
    assert gaps[0].cause == GapCause.UNCLASSIFIED.value


def test_classification_never_raises_on_broken_gap(client, make_user, monkeypatch):
    """A classification failure must degrade to UNCLASSIFIED, never break
    the whole admin page."""
    admin = make_user()
    _seed_unanswered(admin.workspace_id, admin.user_id, "What is the refund policy for annual plans?")

    def _boom(*args, **kwargs):
        raise RuntimeError("retrieval backend down")

    monkeypatch.setattr("app.content_gaps.hybrid_search", _boom)
    db = SessionLocal()
    try:
        gaps = compute_gaps(db, admin.workspace_id, resolved_keys=set())
    finally:
        db.close()
    assert gaps[0].cause == GapCause.UNCLASSIFIED.value


def test_content_gaps_endpoint_includes_new_fields(client, make_user):
    admin = make_user()
    _seed_unanswered(admin.workspace_id, admin.user_id, "What is the refund policy for annual plans?")
    r = client.get("/admin/content-gaps", headers=admin.headers)
    assert r.status_code == 200
    g = r.json()["gaps"][0]
    for field in ("cause", "affected_user_ids", "relevant_document_ids", "suggested_remediation"):
        assert field in g
    assert g["cause"] == GapCause.MISSING_DOCUMENT.value
    assert admin.user_id in g["affected_user_ids"]
