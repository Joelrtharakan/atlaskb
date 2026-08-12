"use client";

import { useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError, api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { FeedbackSummaryResponse } from "@/lib/types";

export function FeedbackView() {
  const [data, setData] = useState<FeedbackSummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .feedbackSummary()
      .then(setData)
      .catch((err) =>
        setError(
          err instanceof ApiError
            ? err.message
            : "Couldn't load feedback. Check the backend is running and refresh.",
        ),
      );
  }, []);

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
        <h1 className="font-display text-3xl font-medium text-ink">Feedback</h1>
        <p className="mt-1 text-sm text-graphite">
          Every thumbs up/down on an answer in this workspace — the read side of the feedback
          loop. Answers marked down are the ones worth reviewing first.
        </p>
      </div>

      {data === null ? (
        <EmptyState title="Reading feedback…" />
      ) : data.entries.length === 0 ? (
        <EmptyState title="No feedback yet —">
          rate an answer with ▲ or ▼ in Chat and it will show up here.
        </EmptyState>
      ) : (
        <>
          <dl className="flex gap-6">
            <div>
              <dt className="font-mono text-xs uppercase tracking-cartouche text-graphite">Up</dt>
              <dd className="marginalia text-2xl text-verdigris">{data.up_count}</dd>
            </div>
            <div>
              <dt className="font-mono text-xs uppercase tracking-cartouche text-graphite">Down</dt>
              <dd className="marginalia text-2xl text-brass">{data.down_count}</dd>
            </div>
          </dl>

          <ul className="flex flex-col gap-3">
            {data.entries.map((e) => (
              <li
                key={e.message_id}
                className={`border-l-2 px-3 py-2 ${
                  e.rating === "up" ? "border-verdigris" : "border-brass"
                }`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded-sm px-1.5 py-0.5 font-mono text-[10px] font-semibold text-linen ${
                      e.rating === "up" ? "bg-verdigris" : "bg-brass"
                    }`}
                  >
                    {e.rating === "up" ? "▲ UP" : "▼ DOWN"}
                  </span>
                  <span className="marginalia text-[0.65rem] text-graphite">
                    {e.user_email ?? "unknown user"} · {formatDateTime(e.created_at)}
                  </span>
                </div>
                {e.question ? (
                  <p className="mt-1.5 text-xs text-graphite">
                    <span className="font-medium text-ink">Q:</span> {e.question}
                  </p>
                ) : null}
                <p className="mt-1 text-sm text-ink">{e.answer}</p>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
