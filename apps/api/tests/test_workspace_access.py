"""Workspace isolation, role gating, per-document ACLs, and invites.

These are the tests that prove the access model actually works — several assert
at the *retrieval* level (a forbidden chunk never appears in ranked results),
not just at the API-response-shape level.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

from app.embeddings import embed_query
from app.models import Invite
from app.rbac import Principal
from app.retrieval import hybrid_search

SECRET = b"# Secret\n\nThe launch code for project ORION is ZULU-7788-RESTRICTED.\n"
OPEN_DOC = b"# Open\n\nThe office coffee machine is on the third floor.\n"


def _upload(client, headers, body=SECRET, name="secret.md"):
    return client.post(
        "/documents",
        headers=headers,
        files={"file": (name, io.BytesIO(body), "text/markdown")},
    )


# --- 1. A viewer cannot upload. ---
def test_viewer_cannot_upload_documents(client, make_user, grant_membership):
    admin = make_user()
    viewer = make_user(create_workspace=False)
    grant_membership(viewer.user_id, admin.workspace_id, "viewer")

    r = _upload(client, viewer.in_ws(admin.workspace_id))
    assert r.status_code == 403
    assert "editor" in r.json()["detail"].lower()


# --- 2. Cross-workspace isolation, including direct-by-id lookup. ---
def test_cannot_reach_another_workspaces_document_by_id(client, make_user, ingest_inline):
    alice = make_user()
    doc_id = _upload(client, alice.headers).json()["id"]

    bob = make_user()  # admin of his own, unrelated workspace
    # Direct id lookup in Bob's own workspace → 404 (never leaks existence).
    assert client.get(f"/documents/{doc_id}", headers=bob.headers).status_code == 404
    # Trying to borrow Alice's workspace id → 403 (Bob isn't a member).
    assert (
        client.get(f"/documents/{doc_id}", headers=bob.in_ws(alice.workspace_id)).status_code
        == 403
    )
    # Alice still sees her own document.
    assert client.get(f"/documents/{doc_id}", headers=alice.headers).status_code == 200


def test_editor_cannot_search_across_workspaces(client, make_user, ingest_inline):
    alice = make_user()
    _upload(client, alice.headers)
    bob = make_user()  # different workspace
    r = client.post("/search", headers=bob.headers, json={"query": "ZULU-7788-RESTRICTED"})
    assert r.status_code == 200
    assert r.json()["results"] == []


# --- 3. Per-document ACL enforced at the RETRIEVAL level. ---
def test_role_restricted_document_excluded_from_retrieval(
    client, make_user, grant_membership, ingest_inline, db
):
    admin = make_user()
    editor = make_user(create_workspace=False)
    viewer = make_user(create_workspace=False)
    grant_membership(editor.user_id, admin.workspace_id, "editor")
    grant_membership(viewer.user_id, admin.workspace_id, "viewer")

    doc_id = _upload(client, admin.headers).json()["id"]

    # Restrict the document to the 'editor' role only.
    r = client.patch(
        f"/documents/{doc_id}/access",
        headers=admin.headers,
        json={"grants": [{"grant_type": "role", "role_or_user_id": "editor"}]},
    )
    assert r.status_code == 200

    ws = admin.workspace_id
    query = "ZULU-7788-RESTRICTED launch code"
    embedding = embed_query(query)

    def chunk_docs(role: str, user_id: str) -> set[str]:
        principal = Principal(user_id=user_id, workspace_id=ws, role=role, auth="jwt")
        hits = hybrid_search(db, query, embedding, principal, top_k=10)
        return {h.document_id for h in hits}

    # Retrieval-level: the restricted doc's chunks never appear for the viewer,
    # but do for the editor (role grant) and the admin (bypass).
    assert doc_id not in chunk_docs("viewer", viewer.user_id)
    assert doc_id in chunk_docs("editor", editor.user_id)
    assert doc_id in chunk_docs("admin", admin.user_id)

    # And the same through the API for search + chat.
    viewer_hits = client.post(
        "/search", headers=viewer.in_ws(ws), json={"query": query}
    ).json()["results"]
    editor_hits = client.post(
        "/search", headers=editor.in_ws(ws), json={"query": query}
    ).json()["results"]
    assert all(c["document_id"] != doc_id for c in viewer_hits)
    assert any(c["document_id"] == doc_id for c in editor_hits)


def test_user_grant_scopes_document_to_named_user(
    client, make_user, grant_membership, ingest_inline, db
):
    admin = make_user()
    allowed = make_user(create_workspace=False)
    excluded = make_user(create_workspace=False)
    grant_membership(allowed.user_id, admin.workspace_id, "viewer")
    grant_membership(excluded.user_id, admin.workspace_id, "viewer")

    doc_id = _upload(client, admin.headers).json()["id"]
    client.patch(
        f"/documents/{doc_id}/access",
        headers=admin.headers,
        json={"grants": [{"grant_type": "user", "role_or_user_id": allowed.user_id}]},
    )

    ws = admin.workspace_id
    embedding = embed_query("ZULU-7788-RESTRICTED")

    def docs_for(user_id):
        p = Principal(user_id=user_id, workspace_id=ws, role="viewer", auth="jwt")
        return {h.document_id for h in hybrid_search(db, "ZULU-7788-RESTRICTED", embedding, p)}

    assert doc_id in docs_for(allowed.user_id)
    assert doc_id not in docs_for(excluded.user_id)


# --- Workspace lifecycle: create, list, members, remove. ---
def test_signup_has_no_workspace_until_created(client, make_user):
    user = make_user(create_workspace=False)
    # No workspace yet → workspace-scoped calls require a workspace and 400.
    assert client.get("/workspaces", headers=user.bearer).json() == []
    assert client.get("/documents", headers=user.bearer).status_code == 400

    ws = client.post("/workspaces", headers=user.bearer, json={"name": "Acme"})
    assert ws.status_code == 201
    assert ws.json()["role"] == "admin"
    listed = client.get("/workspaces", headers=user.bearer).json()
    assert [w["name"] for w in listed] == ["Acme"]


def test_admin_can_remove_member_but_not_last_admin(client, make_user, grant_membership):
    admin = make_user()
    member = make_user(create_workspace=False)
    grant_membership(member.user_id, admin.workspace_id, "editor")
    ws = admin.workspace_id

    assert client.delete(f"/workspaces/{ws}/members/{member.user_id}", headers=admin.headers).status_code == 204
    emails = {m["email"] for m in client.get(f"/workspaces/{ws}/members", headers=admin.headers).json()}
    assert member.email not in emails

    # The sole admin cannot remove themselves (would orphan the workspace).
    assert client.delete(f"/workspaces/{ws}/members/{admin.user_id}", headers=admin.headers).status_code == 400


# --- 4. Invites: only the invited email, and expiry. ---
def test_invite_only_accepted_by_invited_email(client, make_user):
    admin = make_user()
    invitee_email = f"invitee-{admin.user_id[:6]}@example.com"
    invite = client.post(
        f"/workspaces/{admin.workspace_id}/invites",
        headers=admin.headers,
        json={"email": invitee_email, "role": "editor"},
    )
    assert invite.status_code == 201
    token = invite.json()["token"]

    # A different user cannot accept it.
    intruder = make_user(create_workspace=False)
    assert client.post(f"/invites/{token}/accept", headers=intruder.bearer).status_code == 403

    # The invited user can, and lands as an editor.
    invitee = make_user(email=invitee_email, create_workspace=False)
    accepted = client.post(f"/invites/{token}/accept", headers=invitee.bearer)
    assert accepted.status_code == 200
    assert accepted.json()["role"] == "editor"
    # They can now act in the workspace...
    assert client.get("/documents", headers=invitee.in_ws(admin.workspace_id)).status_code == 200
    # ...and the invite can't be reused.
    assert client.post(f"/invites/{token}/accept", headers=invitee.bearer).status_code == 409


def test_invite_preview_is_public(client, make_user):
    admin = make_user()
    email = f"pv-{admin.user_id[:6]}@example.com"
    token = client.post(
        f"/workspaces/{admin.workspace_id}/invites",
        headers=admin.headers,
        json={"email": email, "role": "editor"},
    ).json()["token"]

    # No auth header — the preview must be public so the accept page can render.
    pv = client.get(f"/invites/{token}")
    assert pv.status_code == 200
    body = pv.json()
    assert body["status"] == "valid"
    assert body["email"] == email
    assert body["role"] == "editor"
    assert body["workspace_name"]

    # Unknown token → invalid marker (still 200, no leak).
    assert client.get("/invites/not-a-real-token").json()["status"] == "invalid"


def test_expired_invite_is_rejected(client, make_user, db):
    admin = make_user()
    email = f"late-{admin.user_id[:6]}@example.com"
    token = client.post(
        f"/workspaces/{admin.workspace_id}/invites",
        headers=admin.headers,
        json={"email": email, "role": "viewer"},
    ).json()["token"]

    # Backdate the expiry.
    inv = db.query(Invite).filter(Invite.token == token).one()
    inv.expires_at = datetime.now(UTC) - timedelta(days=1)
    db.commit()

    invitee = make_user(email=email, create_workspace=False)
    assert client.post(f"/invites/{token}/accept", headers=invitee.bearer).status_code == 410


# --- 5. Role management: admin can change roles, editor cannot. ---
def test_admin_changes_role_editor_cannot(client, make_user, grant_membership):
    admin = make_user()
    editor = make_user(create_workspace=False)
    member = make_user(create_workspace=False)
    grant_membership(editor.user_id, admin.workspace_id, "editor")
    grant_membership(member.user_id, admin.workspace_id, "viewer")
    ws = admin.workspace_id

    # Admin promotes the viewer to editor.
    r = client.patch(
        f"/workspaces/{ws}/members/{member.user_id}",
        headers=admin.headers,
        json={"role": "editor"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "editor"

    # An editor cannot change roles.
    r2 = client.patch(
        f"/workspaces/{ws}/members/{member.user_id}",
        headers=editor.in_ws(ws),
        json={"role": "viewer"},
    )
    assert r2.status_code == 403
