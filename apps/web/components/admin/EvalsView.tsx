"use client";

import { useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError, api } from "@/lib/api";
import type { EvalHeadline, EvalResults } from "@/lib/types";

// Quiet results register for the retrieval-QA eval. No animation.

function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

function Mark({ value }: { value: boolean | null }) {
  if (value === null) return <span className="text-graphite">—</span>;
  return <span className={value ? "text-ink" : "text-ink"}>{value ? "✓" : "✗"}</span>;
}

/**
 * The complete final metrics picture (Trust Layer T9.8) — every number here
 * traces to a real eval/results/*.json file (see `source_files` /
 * `missing_files`), never hand-typed. Permission leakage gets its own
 * headline-sized readout since it must read as exactly 0 at a glance.
 */
function Headline({ h }: { h: EvalHeadline }) {
  const leakageOk = h.permission_leakage === 0;
  const rows: [string, string][] = [
    ["Answer accuracy", pct(h.answer_accuracy)],
    ["Retrieval hit rate", pct(h.retrieval_hit_rate)],
    ["Citation accuracy", pct(h.citation_accuracy)],
    ["Citation coverage", pct(h.citation_coverage)],
    ["Conflict detection accuracy", pct(h.conflict_detection_accuracy)],
    ["Refusal accuracy", pct(h.refusal_accuracy)],
    [
      "Adversarial suite",
      h.adversarial_total == null ? "—" : `${h.adversarial_passed}/${h.adversarial_total} passed`,
    ],
    [
      "Prompt injection suite",
      h.prompt_injection_total == null
        ? "—"
        : `${h.prompt_injection_passed}/${h.prompt_injection_total} passed`,
    ],
    ["Avg latency", h.avg_latency_ms == null ? "—" : `${Math.round(h.avg_latency_ms)} ms`],
    ["p95 latency", h.p95_latency_ms == null ? "—" : `${Math.round(h.p95_latency_ms)} ms`],
    ["Cache hit rate (warm)", pct(h.cache_hit_rate)],
  ];

  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="marginalia text-[0.7rem] uppercase tracking-cartouche text-graphite">
          Permission leakage
        </p>
        <p
          className={`mt-1 font-display text-4xl font-medium ${leakageOk ? "text-verdigris" : "text-signal-red"}`}
        >
          {h.permission_leakage == null ? "not measured" : h.permission_leakage}
        </p>
        {!leakageOk && h.permission_leakage != null ? (
          <p className="mt-1 text-sm text-signal-red">
            This must read as 0. It doesn&rsquo;t — treat as a P0 before anything else on this page.
          </p>
        ) : null}
      </div>

      {h.total_questions != null ? (
        <p className="marginalia text-xs text-graphite">
          {h.total_questions} questions evaluated (current full system, T9.1 &ldquo;after&rdquo; config)
        </p>
      ) : null}

      <dl>
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between border-b border-graphite/15 py-2.5">
            <dt className="text-sm text-graphite">{label}</dt>
            <dd className="marginalia text-base text-ink">{value}</dd>
          </div>
        ))}
      </dl>

      {h.missing_files.length > 0 ? (
        <p className="text-xs text-graphite">
          Not yet run (fields above show &ldquo;—&rdquo;): {h.missing_files.join(", ")}
        </p>
      ) : (
        <p className="text-xs text-graphite">
          Every number above comes from: {h.source_files.join(", ")}
        </p>
      )}
    </div>
  );
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

  const hasHeadline = data.headline && data.headline.source_files.length > 0;

  if ((!data.available || !data.metrics) && !hasHeadline) {
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

  if (!data.available || !data.metrics) {
    // Headline metrics exist (T9.1-T9.5 ran) but the T7 per-question run
    // (eval/run_eval.py) specifically hasn't — show what's real, say what isn't.
    return (
      <section className="mx-auto flex h-full max-w-4xl flex-col gap-6 overflow-y-auto p-4 sm:p-8">
        <h1 className="font-display text-3xl font-medium text-ink">Evaluations</h1>
        {data.headline ? <Headline h={data.headline} /> : null}
        <p className="text-sm text-graphite">
          Per-question detail isn&rsquo;t available — run{" "}
          <code className="font-mono text-xs text-ink">uv run python eval/run_eval.py</code> for the
          full T7 breakdown below the headline.
        </p>
      </section>
    );
  }

  const m = data.metrics;
  const metricRows: [string, string][] = [
    ["Answer accuracy", pct(m.answer_accuracy)],
    ["Citation grounding", pct(m.citation_grounding)],
    ["Refusal accuracy (out-of-corpus)", pct(m.refusal_accuracy)],
    ["Retrieval hit rate", pct(m.retrieval_hit_rate)],
    ["Conflict detection accuracy", pct(m.conflict_detection_accuracy)],
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

      {data.headline ? (
        <div className="border border-graphite/25 p-4">
          <h2 className="font-mono text-xs uppercase tracking-cartouche text-graphite">
            Complete picture (T9.1–T9.5)
          </h2>
          <div className="mt-3">
            <Headline h={data.headline} />
          </div>
        </div>
      ) : null}

      <div>
        <h2 className="font-mono text-xs uppercase tracking-cartouche text-graphite">T7 run detail</h2>
        <dl className="mt-2">
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
      </div>

      <div className="overflow-x-auto">
        <h2 className="font-mono text-xs uppercase tracking-cartouche text-graphite">Per question</h2>
        <table className="mt-2 w-full border-collapse text-left text-sm">
          <caption className="sr-only">Per-question evaluation results</caption>
          <thead>
            <tr className="border-b border-graphite/30">
              {["Question", "Hit", "Correct", "Grounded", "Refuse", "Conflict", "ms"].map((h) => (
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
                <td className="px-2 py-2 text-center">
                  <Mark value={r.conflict_correct} />
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
