"use client";

import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError, api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { AuditLogResponse } from "@/lib/types";

const PAGE_SIZE = 50;

export function AuditLogView() {
  const [data, setData] = useState<AuditLogResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);

  const load = useCallback((o: number) => {
    api
      .auditLog(PAGE_SIZE, o)
      .then(setData)
      .catch((err) =>
        setError(
          err instanceof ApiError
            ? err.message
            : "Couldn't load the audit log. Check the backend is running and refresh.",
        ),
      );
  }, []);

  useEffect(() => load(offset), [load, offset]);

  if (error) {
    return (
      <section className="mx-auto max-w-4xl p-4 sm:p-8">
        <p role="alert" className="border border-ink bg-ink/5 px-3 py-2 text-sm text-ink">
          {error}
        </p>
      </section>
    );
  }

  return (
    <section className="mx-auto flex h-full max-w-4xl flex-col gap-6 overflow-y-auto p-4 sm:p-8">
      <div>
        <h1 className="font-display text-3xl font-medium text-ink">Audit Log</h1>
        <p className="mt-1 text-sm text-graphite">
          Every admin/editor action in this workspace — uploads, access changes, membership
          changes, answer feedback.
        </p>
      </div>

      {data === null ? (
        <EmptyState title="Reading the log…" />
      ) : data.entries.length === 0 ? (
        <EmptyState title="Nothing logged yet —">
          actions like uploads, access changes, and membership changes will appear here.
        </EmptyState>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <caption className="sr-only">Audit log entries</caption>
              <thead>
                <tr className="border-b border-graphite/30">
                  {["When", "Action", "Target", "Details"].map((h) => (
                    <th
                      key={h}
                      scope="col"
                      className="px-2 py-2 font-mono text-xs uppercase tracking-cartouche text-graphite"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.entries.map((e) => (
                  <tr key={e.id} className="border-b border-graphite/15">
                    <td className="marginalia px-2 py-2 text-xs text-graphite">
                      {formatDateTime(e.created_at)}
                    </td>
                    <td className="px-2 py-2 font-mono text-xs text-ink">{e.action}</td>
                    <td className="marginalia px-2 py-2 break-all text-xs text-graphite">
                      {e.target ?? "—"}
                    </td>
                    <td className="marginalia px-2 py-2 text-xs text-graphite">
                      {e.meta ? JSON.stringify(e.meta) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
              disabled={offset === 0}
              className="font-mono text-xs uppercase tracking-cartouche text-graphite hover:text-ink disabled:opacity-40"
            >
              ← Newer
            </button>
            <span className="marginalia text-xs text-graphite">
              {offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)} of {data.total}
            </span>
            <button
              type="button"
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= data.total}
              className="font-mono text-xs uppercase tracking-cartouche text-graphite hover:text-ink disabled:opacity-40"
            >
              Older →
            </button>
          </div>
        </>
      )}
    </section>
  );
}
