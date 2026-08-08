"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { ApiError, api } from "@/lib/api";
import type { Member, Role } from "@/lib/types";

const ROLES: Role[] = ["viewer", "editor", "admin"];

// Access-scope editor for a document (admins/editors). No grants = visible to
// all workspace members; otherwise restricted to the selected roles/users
// (the owner and admins always retain access).
export function AccessScopeControl({
  documentId,
  workspaceId,
}: {
  documentId: string;
  workspaceId: string;
}) {
  const [members, setMembers] = useState<Member[]>([]);
  const [roles, setRoles] = useState<Set<Role>>(new Set());
  const [users, setUsers] = useState<Set<string>>(new Set());
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.getDocumentAccess(documentId), api.listMembers(workspaceId)])
      .then(([access, mem]) => {
        setRoles(new Set(access.grants.filter((g) => g.grant_type === "role").map((g) => g.role_or_user_id as Role)));
        setUsers(new Set(access.grants.filter((g) => g.grant_type === "user").map((g) => g.role_or_user_id)));
        setMembers(mem);
        setLoaded(true);
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Couldn't load the access scope."),
      );
  }, [documentId, workspaceId]);

  const restricted = roles.size + users.size > 0;

  function toggle<T>(set: Set<T>, value: T): Set<T> {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    return next;
  }

  async function save() {
    setSaving(true);
    setMsg(null);
    setError(null);
    const grants = [
      ...[...roles].map((r) => ({ grant_type: "role" as const, role_or_user_id: r })),
      ...[...users].map((u) => ({ grant_type: "user" as const, role_or_user_id: u })),
    ];
    try {
      await api.setDocumentAccess(documentId, grants);
      setMsg(restricted ? "Access restricted." : "Visible to all members.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save the access scope.");
    } finally {
      setSaving(false);
    }
  }

  if (error && !loaded) {
    return <p role="alert" className="text-sm text-ink">{error}</p>;
  }
  if (!loaded) return <p className="text-sm text-graphite">Loading access scope…</p>;

  return (
    <div className="border border-graphite/30 bg-linen/50 p-4">
      <p className="font-mono text-xs uppercase tracking-cartouche text-graphite">Access scope</p>
      <p className="mt-1 text-sm text-graphite">
        {restricted
          ? "Restricted — only the roles/people checked below (plus the owner and admins) can see this document."
          : "Visible to all workspace members. Check roles or people to restrict it."}
      </p>

      <fieldset className="mt-3">
        <legend className="sr-only">Roles with access</legend>
        <div className="flex flex-wrap gap-4">
          {ROLES.map((r) => (
            <label key={r} className="flex items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                checked={roles.has(r)}
                onChange={() => setRoles(toggle(roles, r))}
              />
              <span className="font-mono text-xs uppercase tracking-cartouche">{r}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="mt-3">
        <legend className="font-mono text-[0.65rem] uppercase tracking-cartouche text-graphite">
          Specific people
        </legend>
        <div className="mt-1 flex max-h-40 flex-col gap-1 overflow-y-auto">
          {members.map((m) => (
            <label key={m.user_id} className="flex items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                checked={users.has(m.user_id)}
                onChange={() => setUsers(toggle(users, m.user_id))}
              />
              {m.email} <span className="marginalia text-[0.65rem]">· {m.role}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="mt-4 flex items-center gap-3">
        <Button onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save access"}
        </Button>
        {msg ? <span className="text-xs text-ink">{msg}</span> : null}
        {error ? (
          <span role="alert" className="text-xs text-ink">
            {error}
          </span>
        ) : null}
      </div>
    </div>
  );
}
