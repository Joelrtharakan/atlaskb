"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { Connector } from "@/lib/types";

const OAUTH_ERROR_MESSAGES: Record<string, string> = {
  invalid_state: "The connection attempt expired or was tampered with. Try connecting again.",
  token_exchange_failed: "Google didn't accept the connection. Try connecting again.",
  no_refresh_token:
    "Google didn't grant a long-lived connection this time — revoke AtlasKB's access at " +
    "myaccount.google.com/permissions and try connecting again.",
};

function ConnectForm({ onStarted }: { onStarted: () => void }) {
  const [name, setName] = useState("");
  const [folderId, setFolderId] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onConnect(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setPending(true);
    setError(null);
    try {
      const { authorize_url } = await api.authorizeGoogleDrive(name.trim(), folderId.trim() || null);
      onStarted();
      window.location.assign(authorize_url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't start the connection. Try again.");
      setPending(false);
    }
  }

  return (
    <form onSubmit={onConnect} className="flex flex-col gap-4 border border-graphite/30 bg-linen/40 p-4 sm:p-5">
      <div>
        <h2 className="font-display text-lg font-medium text-ink">Connect Google Drive</h2>
        <p className="mt-1 text-sm text-graphite">
          You&rsquo;ll be sent to Google to grant AtlasKB read-only access. Every synced file becomes
          visible to everyone in this workspace, regardless of its Drive-level sharing.
        </p>
      </div>
      <Field
        label="Connector name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Team Drive"
        autoFocus
      />
      <Field
        label="Folder ID (optional)"
        hint="From the folder's Drive URL — .../folders/<this part>. Leave blank to sync every file the connected account can read."
        value={folderId}
        onChange={(e) => setFolderId(e.target.value)}
        placeholder="1a2B3c4D5e6F7g8H9i0J"
      />
      {error ? (
        <p role="alert" className="border border-ink bg-ink/5 px-3 py-2 text-sm text-ink">
          {error}
        </p>
      ) : null}
      <Button type="submit" disabled={pending || !name.trim()} className="self-start">
        {pending ? "Redirecting to Google…" : "Connect with Google →"}
      </Button>
    </form>
  );
}

function StatusPill({ status }: { status: string | null }) {
  const tone =
    status === "ok" ? "text-ink border-ink" : status === "error" ? "text-ink border-ink bg-ink/5" : "text-graphite border-graphite/40";
  return (
    <span className={`inline-block border px-1.5 py-0.5 font-mono text-[0.65rem] uppercase tracking-cartouche ${tone}`}>
      {status ?? "never synced"}
    </span>
  );
}

function ConnectorRow({ connector, onChanged }: { connector: Connector; onChanged: () => void }) {
  const [busy, setBusy] = useState<"sync" | "test" | "delete" | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSync() {
    setBusy("sync");
    setError(null);
    try {
      await api.syncConnectorNow(connector.id);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't queue a sync. Try again.");
    } finally {
      setBusy(null);
    }
  }

  async function onTest() {
    setBusy("test");
    setError(null);
    setTestResult(null);
    try {
      const result = await api.testConnector(connector.id);
      setTestResult(result.ok ? "Connection OK" : (result.error ?? "Connection failed"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't test the connection. Try again.");
    } finally {
      setBusy(null);
    }
  }

  async function onDelete() {
    if (!window.confirm(`Disconnect "${connector.name}"? Documents already synced stay in AtlasKB.`)) return;
    setBusy("delete");
    setError(null);
    try {
      await api.deleteConnector(connector.id);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't disconnect. Try again.");
      setBusy(null);
    }
  }

  return (
    <div className="border-b border-graphite/15 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-mono text-sm text-ink">{connector.name}</p>
          <p className="marginalia mt-0.5 text-xs text-graphite">
            Google Drive · {connector.connected ? "connected" : "not connected"} · last sync{" "}
            {connector.last_sync_at ? formatDateTime(connector.last_sync_at) : "never"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill status={connector.last_sync_status} />
          <Button variant="outline" className="px-2 py-1 text-[0.7rem]" onClick={onTest} disabled={busy !== null}>
            {busy === "test" ? "Testing…" : "Test"}
          </Button>
          <Button variant="outline" className="px-2 py-1 text-[0.7rem]" onClick={onSync} disabled={busy !== null}>
            {busy === "sync" ? "Queuing…" : "Sync now"}
          </Button>
          <Button variant="ghost" className="px-2 py-1 text-[0.7rem]" onClick={onDelete} disabled={busy !== null}>
            {busy === "delete" ? "Disconnecting…" : "Disconnect"}
          </Button>
        </div>
      </div>
      {testResult ? <p className="marginalia mt-2 text-xs text-graphite">{testResult}</p> : null}
      {error ? (
        <p role="alert" className="mt-2 border border-ink bg-ink/5 px-2 py-1.5 text-xs text-ink">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function ConnectorsView() {
  const [connectors, setConnectors] = useState<Connector[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const router = useRouter();
  const searchParams = useSearchParams();

  const load = useCallback(() => {
    api
      .listConnectors()
      .then((rows) => {
        setConnectors(rows);
        setShowForm(rows.length === 0);
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Couldn't load connectors. Check the backend is running."),
      );
  }, []);

  useEffect(() => load(), [load]);

  // The OAuth callback (a server-side redirect, not this page's own fetch)
  // reports success/failure via query params rather than a return value.
  // Snapshot them into state on mount rather than reading `searchParams`
  // directly in render: `router.replace` below strips the param from the
  // URL (so a refresh doesn't replay the banner), and since that causes an
  // immediate re-render, reading straight from `searchParams` would blank
  // the banner out again before anyone could read it.
  const [connected] = useState(() => searchParams.get("connected"));
  const [oauthError] = useState(() => searchParams.get("error"));
  useEffect(() => {
    if (!connected && !oauthError) return;
    router.replace("/admin/connectors");
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on mount only
  }, []);

  if (error) {
    return (
      <section className="mx-auto max-w-3xl p-4 sm:p-8">
        <p role="alert" className="border border-ink bg-ink/5 px-3 py-2 text-sm text-ink">
          {error}
        </p>
      </section>
    );
  }

  return (
    <section className="mx-auto flex h-full max-w-3xl flex-col gap-6 overflow-y-auto p-4 sm:p-8">
      <div>
        <h1 className="font-display text-3xl font-medium text-ink">Connectors</h1>
        <p className="mt-1 text-sm text-graphite">
          Bring documents in automatically from external sources. Google Drive is the only source
          supported today.
        </p>
      </div>

      {connected ? (
        <p role="status" className="border border-ink/40 bg-linen/60 px-3 py-2 text-sm text-ink">
          Connected. Use &ldquo;Sync now&rdquo; below to pull in its files.
        </p>
      ) : null}
      {oauthError ? (
        <p role="alert" className="border border-ink bg-ink/5 px-3 py-2 text-sm text-ink">
          {OAUTH_ERROR_MESSAGES[oauthError] ?? "The connection attempt failed. Try again."}
        </p>
      ) : null}

      {connectors === null ? (
        <EmptyState title="Loading connectors…" />
      ) : (
        <>
          {connectors.length > 0 ? (
            <div className="border border-graphite/30 bg-linen/40 px-4 py-1 sm:px-5">
              {connectors.map((c) => (
                <ConnectorRow key={c.id} connector={c} onChanged={load} />
              ))}
            </div>
          ) : null}

          {showForm ? (
            <ConnectForm onStarted={() => setShowForm(false)} />
          ) : (
            <Button variant="outline" className="self-start" onClick={() => setShowForm(true)}>
              + Connect another source
            </Button>
          )}
        </>
      )}
    </section>
  );
}
