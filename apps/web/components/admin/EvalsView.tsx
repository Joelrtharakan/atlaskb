"use client";

import { useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError, api } from "@/lib/api";
import type { EvalResults } from "@/lib/types";

// Quiet results register for the retrieval-QA eval. No animation.

function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

function Mark({ value }: { value: boolean | null }) {
  if (value === null) return <span className="text-graphite">—</span>;
  return <span className={value ? "text-ink" : "text-ink"}>{value ? "✓" : "✗"}</span>;
}

export function EvalsView() {
  const [data, setData] = useState<EvalResults | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .evals()
      .then(setData)
      .catch((err) =>
        setError(
          err instanceof ApiError
            ? err.message
            : "Couldn't load eval results. Check the backend is running and refresh.",
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

  if (data === null) {
    return (
      <section className="mx-auto max-w-4xl p-4 sm:p-8">
        <EmptyState title="Reading the latest run…" />
      </section>
    );
  }

  if (!data.available || !data.metrics) {
    return (
      <section className="mx-auto max-w-4xl p-4 sm:p-8">
        <h1 className="font-display text-3xl font-medium text-ink">Evaluations</h1>
        <div className="mt-6 border border-graphite/30">
          <EmptyState title="No evaluation has been run yet —">
            run{" "}
            <code className="font-mono text-xs text-ink">uv run python eval/run_eval.py</code> from
            the repo root to measure retrieval and grounding quality, then refresh.
          </EmptyState>
        </div>
      </section>
    );
  }

  const m = data.metrics;
  const metricRows: [string, string][] = [
    ["Answer accuracy", pct(m.answer_accuracy)],
    ["Citation grounding", pct(m.citation_grounding)],
    ["Refusal accuracy (out-of-corpus)", pct(m.refusal_accuracy)],
    ["Retrieval hit rate", pct(m.retrieval_hit_rate)],
    ["Avg tokens / query", String(m.avg_tokens_per_query)],
    ["Latency p50", `${Math.round(m.latency_p50_ms)} ms`],
    ["Latency p95", `${Math.round(m.latency_p95_ms)} ms`],
  ];

  return (
    <section className="mx-auto flex h-full max-w-4xl flex-col gap-6 overflow-y-auto p-4 sm:p-8">
      <div>
        <h1 className="font-display text-3xl font-medium text-ink">Evaluations</h1>
        <p className="marginalia mt-1 text-xs text-graphite">
          model {data.model} · {data.dataset_size} questions over {data.corpus_size} documents ·{" "}
          {data.generated_at ? new Date(data.generated_at).toLocaleString() : ""}
        </p>
      </div>

      <dl>
        {metricRows.map(([label, value]) => (
          <div
            key={label}
            className="flex items-baseline justify-between border-b border-graphite/15 py-3"
          >
            <dt className="text-sm text-graphite">{label}</dt>
            <dd className="marginalia text-base text-ink">{value}</dd>
          </div>
        ))}
      </dl>

      <div className="overflow-x-auto">
        <h2 className="font-mono text-xs uppercase tracking-cartouche text-graphite">Per question</h2>
        <table className="mt-2 w-full border-collapse text-left text-sm">
          <caption className="sr-only">Per-question evaluation results</caption>
          <thead>
            <tr className="border-b border-graphite/30">
              {["Question", "Hit", "Correct", "Grounded", "Refuse", "ms"].map((h) => (
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
            {(data.results ?? []).map((r, i) => (
              <tr key={i} className="border-b border-graphite/15">
                <td className="px-2 py-2 text-ink">{r.question}</td>
                <td className="px-2 py-2 text-center">
                  <Mark value={r.retrieval_hit} />
                </td>
                <td className="px-2 py-2 text-center">
                  <Mark value={r.answer_correct} />
                </td>
                <td className="px-2 py-2 text-center">
                  <Mark value={r.citation_grounded} />
                </td>
                <td className="px-2 py-2 text-center">
                  <Mark value={r.refusal_correct} />
                </td>
                <td className="marginalia px-2 py-2 text-right text-xs">{Math.round(r.latency_ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
