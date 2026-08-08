"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { ContourProgress } from "@/components/ui/ContourProgress";
import { Field } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { InvitePreview } from "@/lib/types";
import { useWorkspace } from "@/lib/workspace";

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen p-3 sm:p-5">
      <div className="neatline flex min-h-[calc(100vh-1.5rem)] flex-col items-center justify-center px-6 sm:min-h-[calc(100vh-2.5rem)]">
        <div className="w-full max-w-sm">
          <p className="marginalia mb-3 text-[0.7rem] uppercase tracking-cartouche text-graphite">
            Workspace invite
          </p>
          {children}
        </div>
      </div>
    </main>
  );
}

export function AcceptInviteView({ token }: { token: string }) {
  const auth = useAuth();
  const { setActive, refresh } = useWorkspace();

  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getInvite(token)
      .then(setPreview)
      .catch(() => setPreview({ status: "invalid", email: null, role: null, workspace_id: null, workspace_name: null }));
  }, [token]);

  async function finishAccept() {
    const res = await api.acceptInvite(token);
    await refresh();
    setActive(res.workspace_id);
    window.location.assign("/documents");
  }

  // Already signed in as the invited person → one-click accept.
  async function acceptAsCurrent() {
    setBusy(true);
    setError(null);
    try {
      await finishAccept();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't accept the invite.");
      setBusy(false);
    }
  }

  // New (or returning) invitee: set a password → create account (or log in) → join.
  async function createAndJoin(e: FormEvent) {
    e.preventDefault();
    if (!preview?.email) return;
    setBusy(true);
    setError(null);
    try {
      try {
        await auth.signup(preview.email, password); // signs up + logs in
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          // The email already has an account — log in with the given password.
          try {
            await auth.login(preview.email, password);
          } catch {
            setError("This email already has an account. Enter its password to log in and join.");
            setBusy(false);
            return;
          }
        } else {
          throw err;
        }
      }
      await finishAccept();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Couldn't create your account. Try again.",
      );
      setBusy(false);
    }
  }

  if (!auth.ready || preview === null) {
    return (
      <Frame>
        <div className="flex items-center gap-3">
          <ContourProgress size={28} label="Loading invite" />
          <span className="text-sm text-graphite">Loading your invite…</span>
        </div>
      </Frame>
    );
  }

  if (preview.status !== "valid") {
    const copy = {
      expired: "This invite has expired. Ask an admin to send a new one.",
      accepted: "This invite has already been used.",
      invalid: "This invite link isn’t valid.",
    }[preview.status];
    return (
      <Frame>
        <h1 className="font-display text-2xl font-medium text-ink">Invite unavailable</h1>
        <p className="mt-2 text-sm text-graphite">{copy}</p>
        <Link href="/login" className="mt-6 inline-block">
          <Button variant="outline">Go to AtlasKB</Button>
        </Link>
      </Frame>
    );
  }

  const invitedEmail = preview.email ?? "";
  const roleLabel = preview.role ?? "member";
  const wsLabel = preview.workspace_name ?? "the workspace";

  // Signed in as someone else → they must switch accounts to accept.
  if (auth.isAuthenticated && auth.email && auth.email.toLowerCase() !== invitedEmail.toLowerCase()) {
    return (
      <Frame>
        <h1 className="font-display text-2xl font-medium text-ink">Wrong account</h1>
        <p className="mt-2 text-sm text-graphite">
          You&rsquo;re signed in as <span className="text-ink">{auth.email}</span>, but this invite
          is for <span className="text-ink">{invitedEmail}</span>. Log out and open the link again.
        </p>
        <Button
          className="mt-6"
          onClick={() => {
            auth.logout();
            window.location.reload();
          }}
        >
          Log out
        </Button>
      </Frame>
    );
  }

  // Signed in as the invited person → one-click accept.
  if (auth.isAuthenticated && auth.email?.toLowerCase() === invitedEmail.toLowerCase()) {
    return (
      <Frame>
        <h1 className="font-display text-2xl font-medium text-ink">Join {wsLabel}</h1>
        <p className="mt-2 text-sm text-graphite">
          You&rsquo;ve been invited as <span className="text-ink">{roleLabel}</span>.
        </p>
        {error ? (
          <p role="alert" className="mt-3 border border-ink bg-ink/5 px-3 py-2 text-sm text-ink">
            {error}
          </p>
        ) : null}
        <Button className="mt-6 w-full" onClick={acceptAsCurrent} disabled={busy}>
          {busy ? "Joining…" : `Accept & join as ${roleLabel}`}
        </Button>
      </Frame>
    );
  }

  // Not signed in → set a password and join in one step.
  return (
    <Frame>
      <h1 className="font-display text-2xl font-medium text-ink">Join {wsLabel}</h1>
      <p className="mt-2 text-sm text-graphite">
        You&rsquo;ve been invited as <span className="text-ink">{roleLabel}</span>. Set a password to
        create your account and join.
      </p>
      <form onSubmit={createAndJoin} className="mt-6 flex flex-col gap-4" noValidate>
        <Field label="Email" value={invitedEmail} readOnly disabled />
        <Field
          label="Password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          hint="At least 8 characters."
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error ? (
          <p role="alert" className="border border-ink bg-ink/5 px-3 py-2 text-sm text-ink">
            {error}
          </p>
        ) : null}
        <Button type="submit" disabled={busy || password.length < 8} className="w-full">
          {busy ? "Joining…" : "Create account & join"}
        </Button>
      </form>
      <p className="mt-4 text-xs text-graphite">
        Already have an account with this email? Enter its password above — we&rsquo;ll log you in
        and join you.
      </p>
    </Frame>
  );
}
