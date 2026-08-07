"use client";

import { useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError, api } from "@/lib/api";
import type { Analytics } from "@/lib/types";

// A quiet register, not a dashboard: hairline-ruled rows, system numbers in mono.
// No beacon/meridian, no animation — this surface holds still (design plan §6).

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="flex items-baseline justify-between border-b border-graphite/15 py-3">
      <dt className="text-sm text-graphite">{label}</dt>
      <dd className="marginalia text-base text-ink">{value}</dd>
    </div>
  );
}

export function AnalyticsView() {
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .analytics()
      .then(setData)
      .catch((err) =>
        setError(
          err instanceof ApiError
            ? err.message
            : "Couldn't load analytics. Check the backend is running and refresh.",
        ),
      );
  }, []);

  return (
    <section className="mx-auto flex h-full max-w-3xl flex-col gap-6 overflow-y-auto p-4 sm:p-8">
      <div>
        <h1 className="font-display text-3xl font-medium text-ink">Analytics</h1>
        <p className="mt-1 text-sm text-graphite">
          A quiet register of this workspace&rsquo;s activity — counted from the live database.
        </p>
      </div>

      {error ? (
        <p role="alert" className="border border-ink bg-ink/5 px-3 py-2 text-sm text-ink">
          {error}
        </p>
      ) : data === null ? (
        <EmptyState title="Reading the register…" />
      ) : (
        <>
          <dl>
            <Stat label="Documents" value={data.documents_total} />
            {Object.entries(data.documents_by_status).map(([status, n]) => (
              <Stat key={status} label={`  ↳ ${status}`} value={n} />
            ))}
            <Stat label="Chunks indexed" value={data.chunks_total} />
            <Stat label="Conversations" value={data.conversations_total} />
            <Stat label="Messages" value={data.messages_total} />
            <Stat label="Members" value={data.members_total} />
            <Stat label="Active API keys" value={data.active_api_keys} />
            <Stat label="Semantic-cache entries (Redis)" value={data.cache_entries} />
          </dl>

          <div>
            <h2 className="font-mono text-xs uppercase tracking-cartouche text-graphite">
              Questions asked · last 7 days
            </h2>
            {data.questions_last_7_days.length === 0 ? (
              <p className="mt-2 text-sm text-graphite">
                No questions yet — ask one on the chat page and it will show up here.
              </p>
            ) : (
              <ul className="mt-2 flex flex-col gap-1">
                {data.questions_last_7_days.map((d) => (
                  <li key={d.day} className="marginalia flex items-center gap-3 text-xs">
                    <span className="w-24 text-graphite">{d.day}</span>
                    <span
                      aria-hidden
                      className="inline-block h-2 bg-ink/70"
                      style={{ width: `${Math.min(100, d.count * 12)}px` }}
                    />
                    <span className="text-ink">{d.count}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </section>
  );
}
