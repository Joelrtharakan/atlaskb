"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Member, Role } from "@/lib/types";
import { useWorkspace } from "@/lib/workspace";

import { RoleFlag } from "./RoleFlag";

const ROLES: Role[] = ["viewer", "editor", "admin"];

export function MembersView() {
  const { active, role } = useWorkspace();
  const workspaceId = active?.id ?? "";
  const isAdmin = role === "admin";

  const [members, setMembers] = useState<Member[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<Role>("viewer");
  const [inviteMsg, setInviteMsg] = useState<string | null>(null);
  const [inviteErr, setInviteErr] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!workspaceId) return;
    try {
      setMembers(await api.listMembers(workspaceId));
      setError(null);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Couldn't load members. Refresh to try again.",
      );
    }
  }, [workspaceId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function onInvite(e: FormEvent) {
    e.preventDefault();
    setInviteErr(null);
    setInviteMsg(null);
    try {
      const invite = await api.invite(workspaceId, inviteEmail.trim(), inviteRole);
      setInviteMsg(`Invite created. Share this link: ${invite.invite_url}`);
      setInviteEmail("");
    } catch (err) {
      setInviteErr(err instanceof ApiError ? err.message : "Couldn't create the invite.");
    }
  }

  async function onRoleChange(userId: string, newRole: Role) {
    try {
      await api.changeRole(workspaceId, userId, newRole);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't change that member's role.");
    }
  }

  async function onRemove(userId: string) {
    try {
      await api.removeMember(workspaceId, userId);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't remove that member.");
    }
  }

  return (
    <section className="mx-auto flex h-full max-w-3xl flex-col gap-6 overflow-y-auto p-4 sm:p-8">
      <div>
        <h1 className="font-display text-3xl font-medium text-ink">Members</h1>
        <p className="mt-1 text-sm text-graphite">
          Who can reach <span className="text-ink">{active?.name}</span>, and what they can do.
        </p>
      </div>

      {isAdmin ? (
        <form onSubmit={onInvite} className="border border-graphite/30 bg-linen/50 p-4">
          <p className="font-mono text-xs uppercase tracking-cartouche text-graphite">Invite a member</p>
          <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1">
              <Field
                label="Email"
                type="email"
                required
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                placeholder="teammate@example.com"
              />
            </div>
            <div>
              <label
                htmlFor="invite-role"
                className="font-mono text-xs uppercase tracking-cartouche text-graphite"
              >
                Role
              </label>
              <select
                id="invite-role"
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as Role)}
                className="mt-1.5 block border border-graphite/50 bg-linen/60 px-3 py-2 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter"
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
            <Button type="submit" disabled={!inviteEmail.trim()}>
              Create invite
            </Button>
          </div>
          {inviteMsg ? (
            <p className="mt-3 flex items-start gap-2 break-all text-xs text-ink">
              <RoleFlag key={inviteMsg} role={inviteRole} plant />
              <span>{inviteMsg}</span>
            </p>
          ) : null}
          {inviteErr ? (
            <p role="alert" className="mt-3 border border-ink bg-ink/5 px-3 py-2 text-sm text-ink">
              {inviteErr}
            </p>
          ) : null}
        </form>
      ) : null}

      {error ? (
        <p role="alert" className="border border-ink bg-ink/5 px-3 py-2 text-sm text-ink">
          {error}
        </p>
      ) : null}

      <div className="border border-graphite/30">
        {members === null ? (
          <EmptyState title="Loading members…" />
        ) : (
          <table className="w-full border-collapse text-left text-sm">
            <caption className="sr-only">Workspace members</caption>
            <thead>
              <tr className="border-b border-graphite/30">
                {["Email", "Role", "Joined", ""].map((h, i) => (
                  <th
                    key={i}
                    className="px-4 py-2 font-mono text-xs uppercase tracking-cartouche text-graphite"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <tr key={m.user_id} className="border-b border-graphite/15 last:border-0">
                  <td className="px-4 py-3 text-ink">
                    <span className="flex items-center gap-2">
                      <RoleFlag role={m.role} plant />
                      {m.email}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {isAdmin ? (
                      <select
                        aria-label={`Role for ${m.email}`}
                        value={m.role}
                        onChange={(e) => onRoleChange(m.user_id, e.target.value as Role)}
                        className="border border-graphite/40 bg-linen/60 px-2 py-1 font-mono text-xs text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter"
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {r}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="marginalia text-xs">{m.role}</span>
                    )}
                  </td>
                  <td className="marginalia px-4 py-3 text-xs">{formatDate(m.joined_at)}</td>
                  <td className="px-4 py-3 text-right">
                    {isAdmin ? (
                      <button
                        type="button"
                        onClick={() => onRemove(m.user_id)}
                        className="font-mono text-xs uppercase tracking-cartouche text-graphite hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter"
                      >
                        Remove
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
