"""Workspace management and role enforcement."""

from __future__ import annotations

import io


def _upload(client, headers, tenant_id=None):
    if tenant_id:
        headers = {**headers, "X-Tenant-Id": tenant_id}
    return client.post(
        "/documents",
        headers=headers,
        files={"file": ("d.md", io.BytesIO(b"# D\n\ncontent\n"), "text/markdown")},
    )


def test_create_and_list_workspaces(client, make_user):
    user = make_user()
    created = client.post("/workspaces", headers=user.headers, json={"name": "Acme"})
    assert created.status_code == 201
    assert created.json()["role"] == "admin"

    workspaces = client.get("/workspaces", headers=user.headers).json()
    names = {w["name"] for w in workspaces}
    assert "Acme" in names
    assert len(workspaces) == 2  # personal + Acme


def test_invite_existing_user_and_access(client, make_user):
    admin = make_user()
    member = make_user()
    r = client.post(
        f"/workspaces/{admin.tenant_id}/invite",
        headers=admin.headers,
        json={"email": member.email, "role": "editor"},
    )
    assert r.status_code == 201

    # The member can now act in the admin's workspace via X-Tenant-Id.
    members = client.get(
        f"/workspaces/{admin.tenant_id}/members",
        headers={**member.headers, "X-Tenant-Id": admin.tenant_id},
    )
    assert members.status_code == 200
    emails = {m["email"] for m in members.json()}
    assert {admin.email, member.email} <= emails


def test_invite_unknown_email_404_and_duplicate_409(client, make_user):
    admin = make_user()
    member = make_user()
    assert (
        client.post(
            f"/workspaces/{admin.tenant_id}/invite",
            headers=admin.headers,
            json={"email": "ghost-unregistered@example.com", "role": "viewer"},
        ).status_code
        == 404
    )
    client.post(
        f"/workspaces/{admin.tenant_id}/invite",
        headers=admin.headers,
        json={"email": member.email, "role": "viewer"},
    )
    dup = client.post(
        f"/workspaces/{admin.tenant_id}/invite",
        headers=admin.headers,
        json={"email": member.email, "role": "viewer"},
    )
    assert dup.status_code == 409


def test_non_admin_cannot_invite(client, make_user):
    admin = make_user()
    member = make_user()
    third = make_user()
    client.post(
        f"/workspaces/{admin.tenant_id}/invite",
        headers=admin.headers,
        json={"email": member.email, "role": "editor"},
    )
    # An editor is not an admin → cannot invite.
    r = client.post(
        f"/workspaces/{admin.tenant_id}/invite",
        headers={**member.headers, "X-Tenant-Id": admin.tenant_id},
        json={"email": third.email, "role": "viewer"},
    )
    assert r.status_code == 403


def test_role_gates_upload_and_can_be_promoted(client, make_user):
    admin = make_user()
    member = make_user()
    client.post(
        f"/workspaces/{admin.tenant_id}/invite",
        headers=admin.headers,
        json={"email": member.email, "role": "viewer"},
    )

    # Viewer cannot upload...
    assert _upload(client, member.headers, admin.tenant_id).status_code == 403

    # Promote to editor.
    up = client.patch(
        f"/workspaces/{admin.tenant_id}/members/{member.user_id}",
        headers=admin.headers,
        json={"role": "editor"},
    )
    assert up.status_code == 200
    assert up.json()["role"] == "editor"

    # ...now they can.
    assert _upload(client, member.headers, admin.tenant_id).status_code == 201


def test_outsider_cannot_list_members(client, make_user):
    admin = make_user()
    outsider = make_user()
    # Outsider presents someone else's tenant id → 403 (not a member).
    r = client.get(
        f"/workspaces/{admin.tenant_id}/members",
        headers={**outsider.headers, "X-Tenant-Id": admin.tenant_id},
    )
    assert r.status_code == 403
