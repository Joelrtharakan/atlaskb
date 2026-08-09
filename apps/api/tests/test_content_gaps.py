"""Content-gap detection + resolve (Fog of War backend)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db import SessionLocal
from app.llm import CANNOT_ANSWER
from app.models import Conversation, Message


def _seed_unanswered(workspace_id: str, user_id: str, questions: list[str]) -> None:
    """Insert conversations where each question got the CANNOT_ANSWER reply."""
    s = SessionLocal()
    try:
        base = datetime.now(UTC)
        for i, q in enumerate(questions):
            convo = Conversation(workspace_id=workspace_id, user_id=user_id, title=q[:50])
            s.add(convo)
            s.flush()
            s.add(
                Message(
                    conversation_id=convo.id,
                    workspace_id=workspace_id,
                    role="user",
                    content=q,
                    created_at=base + timedelta(seconds=i * 2),
                )
            )
            s.add(
                Message(
                    conversation_id=convo.id,
                    workspace_id=workspace_id,
                    role="assistant",
                    content=CANNOT_ANSWER,
                    created_at=base + timedelta(seconds=i * 2 + 1),
                )
            )
        s.commit()
    finally:
        s.close()


def test_content_gaps_listed_and_resolvable(client, make_user):
    admin = make_user()
    _seed_unanswered(
        admin.workspace_id,
        admin.user_id,
        ["What is the refund policy?", "How many vacation days do contractors get?"],
    )

    r = client.get("/admin/content-gaps", headers=admin.headers)
    assert r.status_code == 200
    gaps = r.json()["gaps"]
    assert len(gaps) >= 1
    g = gaps[0]
    for field in ("key", "query", "count", "x", "y", "radius", "resolved"):
        assert field in g
    assert g["resolved"] is False
    assert 0 <= g["x"] <= 1 and 0 <= g["y"] <= 1

    # Resolving clears that gap's fog.
    key = g["key"]
    r2 = client.post(f"/admin/content-gaps/{key}/resolve", headers=admin.headers)
    assert r2.status_code == 200
    resolved = {x["key"]: x["resolved"] for x in r2.json()["gaps"]}
    assert resolved[key] is True


def test_content_gaps_admin_only(client, make_user, grant_membership):
    admin = make_user()
    viewer = make_user(create_workspace=False)
    grant_membership(viewer.user_id, admin.workspace_id, "viewer")
    r = client.get("/admin/content-gaps", headers=viewer.in_ws(admin.workspace_id))
    assert r.status_code == 403


def test_query_volume_counts_user_messages(client, make_user):
    admin = make_user()
    _seed_unanswered(admin.workspace_id, admin.user_id, ["q one", "q two"])
    r = client.get("/admin/query-volume?days=7", headers=admin.headers)
    assert r.status_code == 200
    total = sum(p["count"] for p in r.json()["points"])
    assert total >= 2  # two user questions seeded today
