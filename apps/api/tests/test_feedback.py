"""Feedback loop + audit log (Trust Layer T6)."""

from __future__ import annotations


def test_rate_message_up_and_down(client, auth_headers, stub_llm):
    r = client.post("/chat", headers=auth_headers, json={"question": "hello?"})
    message_id = r.json()["message_id"]
    assert message_id

    up = client.post(
        f"/chat/messages/{message_id}/feedback", headers=auth_headers, json={"rating": "up"}
    )
    assert up.status_code == 200
    assert up.json() == {"message_id": message_id, "rating": "up"}

    # Re-rating overwrites rather than accumulating.
    down = client.post(
        f"/chat/messages/{message_id}/feedback", headers=auth_headers, json={"rating": "down"}
    )
    assert down.status_code == 200
    assert down.json()["rating"] == "down"


def test_rate_message_requires_ownership(client, make_user, grant_membership, stub_llm):
    owner = make_user()
    r = client.post("/chat", headers=owner.headers, json={"question": "hello?"})
    message_id = r.json()["message_id"]

    other = make_user(create_workspace=False)
    grant_membership(other.user_id, owner.workspace_id, "viewer")
    r2 = client.post(
        f"/chat/messages/{message_id}/feedback",
        headers=other.in_ws(owner.workspace_id),
        json={"rating": "up"},
    )
    assert r2.status_code == 404


def test_rate_message_rejects_user_turn(client, auth_headers, stub_llm):
    """Only the assistant's own message can be rated, not the user's question."""
    from app.db import SessionLocal
    from app.models import Message

    r = client.post("/chat", headers=auth_headers, json={"question": "hello?"})
    convo_id = r.json()["conversation_id"]

    db = SessionLocal()
    user_msg = (
        db.query(Message)
        .filter(Message.conversation_id == convo_id, Message.role == "user")
        .first()
    )
    db.close()

    r2 = client.post(
        f"/chat/messages/{user_msg.id}/feedback", headers=auth_headers, json={"rating": "up"}
    )
    assert r2.status_code == 404


def test_conversation_history_reflects_feedback(client, auth_headers, stub_llm):
    r = client.post("/chat", headers=auth_headers, json={"question": "hello?"})
    convo_id = r.json()["conversation_id"]
    message_id = r.json()["message_id"]

    client.post(f"/chat/messages/{message_id}/feedback", headers=auth_headers, json={"rating": "up"})

    detail = client.get(f"/conversations/{convo_id}", headers=auth_headers).json()
    assistant_msg = next(m for m in detail["messages"] if m["role"] == "assistant")
    assert assistant_msg["id"] == message_id
    assert assistant_msg["feedback"] == "up"
    user_msg = next(m for m in detail["messages"] if m["role"] == "user")
    assert user_msg["feedback"] is None


def test_admin_feedback_summary(client, make_user, grant_membership, stub_llm):
    admin = make_user()
    asker = make_user(create_workspace=False)
    grant_membership(asker.user_id, admin.workspace_id, "viewer")

    r = client.post("/chat", headers=asker.in_ws(admin.workspace_id), json={"question": "hello?"})
    message_id = r.json()["message_id"]
    client.post(
        f"/chat/messages/{message_id}/feedback",
        headers=asker.in_ws(admin.workspace_id),
        json={"rating": "down"},
    )

    r2 = client.get("/admin/feedback", headers=admin.headers)
    assert r2.status_code == 200
    body = r2.json()
    assert body["down_count"] == 1
    assert body["up_count"] == 0
    assert body["entries"][0]["message_id"] == message_id
    assert body["entries"][0]["user_email"] == asker.email
    assert body["entries"][0]["question"] == "hello?"


def test_admin_feedback_requires_admin_role(client, make_user, grant_membership):
    owner = make_user()
    viewer = make_user(create_workspace=False)
    grant_membership(viewer.user_id, owner.workspace_id, "viewer")
    r = client.get("/admin/feedback", headers=viewer.in_ws(owner.workspace_id))
    assert r.status_code == 403


def test_admin_audit_log_lists_actions(client, auth_headers):
    import io

    client.post(
        "/documents",
        headers=auth_headers,
        files={"file": ("x.md", io.BytesIO(b"# X\n\ncontent"), "text/markdown")},
    )
    r = client.get("/admin/audit-log", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any(e["action"] == "document.upload" for e in body["entries"])


def test_admin_audit_log_pagination(client, auth_headers):
    import io

    for i in range(3):
        client.post(
            "/documents",
            headers=auth_headers,
            files={"file": (f"x{i}.md", io.BytesIO(b"# X\n\ncontent"), "text/markdown")},
        )
    r = client.get("/admin/audit-log?limit=2&offset=0", headers=auth_headers)
    body = r.json()
    assert len(body["entries"]) == 2
    assert body["total"] >= 3
    assert body["limit"] == 2
