"""Per-document ACL overrides within a tenant."""

from __future__ import annotations

import io

DOC = b"# Ops\n\nThe database password rotation happens every 90 days.\n"


def _upload(client, headers):
    return client.post(
        "/documents",
        headers=headers,
        files={"file": ("ops.md", io.BytesIO(DOC), "text/markdown")},
    ).json()


def _add_member(client, admin, invitee_email, role="viewer"):
    return client.post(
        f"/workspaces/{admin.tenant_id}/invite",
        headers=admin.headers,
        json={"email": invitee_email, "role": role},
    )


def test_member_sees_unrestricted_document(client, make_user, ingest_inline):
    admin = make_user()
    member = make_user()
    _add_member(client, admin, member.email, role="editor")
    doc = _upload(client, admin.headers)

    hdr = {**member.headers, "X-Tenant-Id": admin.tenant_id}
    # No ACL set → open to all members.
    assert client.get(f"/documents/{doc['id']}", headers=hdr).status_code == 200
    r = client.post("/search", headers=hdr, json={"query": "password rotation 90 days"})
    assert any("rotation" in c["text"] for c in r.json()["results"])


def test_acl_restricts_document_to_named_users(client, make_user, ingest_inline):
    admin = make_user()
    allowed = make_user()
    excluded = make_user()
    _add_member(client, admin, allowed.email, role="viewer")
    _add_member(client, admin, excluded.email, role="viewer")

    doc = _upload(client, admin.headers)

    # Restrict the document to `allowed` only.
    r = client.put(
        f"/documents/{doc['id']}/acl",
        headers=admin.headers,
        json={"user_ids": [allowed.user_id]},
    )
    assert r.status_code == 200

    allowed_hdr = {**allowed.headers, "X-Tenant-Id": admin.tenant_id}
    excluded_hdr = {**excluded.headers, "X-Tenant-Id": admin.tenant_id}

    # Allowed user still sees it; excluded member no longer can.
    assert client.get(f"/documents/{doc['id']}", headers=allowed_hdr).status_code == 200
    assert client.get(f"/documents/{doc['id']}", headers=excluded_hdr).status_code == 404

    # Retrieval respects the ACL too.
    allowed_hits = client.post(
        "/search", headers=allowed_hdr, json={"query": "password rotation"}
    ).json()["results"]
    excluded_hits = client.post(
        "/search", headers=excluded_hdr, json={"query": "password rotation"}
    ).json()["results"]
    assert any("rotation" in c["text"] for c in allowed_hits)
    assert excluded_hits == []


def test_admin_bypasses_acl(client, make_user, ingest_inline):
    admin = make_user()
    other = make_user()
    _add_member(client, admin, other.email, role="viewer")
    doc = _upload(client, admin.headers)
    # Restrict to `other` only — but admin can always see tenant documents.
    client.put(
        f"/documents/{doc['id']}/acl",
        headers=admin.headers,
        json={"user_ids": [other.user_id]},
    )
    assert client.get(f"/documents/{doc['id']}", headers=admin.headers).status_code == 200


def test_acl_must_reference_tenant_members(client, make_user, ingest_inline):
    admin = make_user()
    outsider = make_user()  # never invited
    doc = _upload(client, admin.headers)
    r = client.put(
        f"/documents/{doc['id']}/acl",
        headers=admin.headers,
        json={"user_ids": [outsider.user_id]},
    )
    assert r.status_code == 400


def test_non_owner_member_cannot_set_acl(client, make_user, ingest_inline):
    admin = make_user()
    editor = make_user()
    _add_member(client, admin, editor.email, role="editor")
    doc = _upload(client, admin.headers)  # owned by admin

    r = client.put(
        f"/documents/{doc['id']}/acl",
        headers={**editor.headers, "X-Tenant-Id": admin.tenant_id},
        json={"user_ids": [editor.user_id]},
    )
    assert r.status_code == 403
