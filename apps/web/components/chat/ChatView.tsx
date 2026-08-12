"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { Atlas2DFallback } from "@/components/living-atlas/Atlas2DFallback";
import { layoutFromDocuments } from "@/components/living-atlas/layout";
import { useCapabilities } from "@/components/living-atlas/use-capabilities";
import { ContourProgress } from "@/components/ui/ContourProgress";
import { ApiError, api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { ChatResponse, Conflict, DocumentOut, Evidence } from "@/lib/types";

import { numberSources, renderAnswerWithCitations } from "./citations";

// The Three.js scene is loaded on demand (client-only), so pages that never
// show the atlas — and degraded sessions that fall back to 2D — never pay for
// the WebGL bundle.
const LivingAtlas = dynamic(() => import("@/components/living-atlas/LivingAtlas"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center">
      <ContourProgress size={40} label="Loading the atlas" />
    </div>
  ),
});

type Entry =
  | { kind: "question"; id: string; at: string; text: string }
  | { kind: "pending"; id: string }
  | { kind: "answer"; id: string; at: string; resp: ChatResponse; question: string }
  | { kind: "error"; id: string; at: string; message: string };

type AtlasState = {
  activeIds: string[];
  citedIds: string[];
  staleIds: string[];
  conflictPairs: [string, string][];
  focus: boolean;
  phase: "idle" | "retrieving" | "answered" | "settling";
};

const IDLE: AtlasState = {
  activeIds: [],
  citedIds: [],
  staleIds: [],
  conflictPairs: [],
  focus: false,
  phase: "idle",
};

/** Document ids whose evidence is aging — same > 0.5 threshold used everywhere
 * else staleness is shown (Dashboard relief map, "Why this answer?"). */
function staleDocIds(evidence: Evidence[] | undefined): string[] {
  return Array.from(new Set((evidence ?? []).filter((e) => e.staleness > 0.5).map((e) => e.document_id)));
}

/** Every conflict's document_ids collapsed into unordered pairs — a 3+-way
 * conflict (rare) fans out to every pairwise link rather than being dropped. */
function conflictDocPairs(conflicts: ChatResponse["conflicts"]): [string, string][] {
  const pairs: [string, string][] = [];
  for (const c of conflicts ?? []) {
    const ids = c.document_ids;
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        pairs.push([ids[i], ids[j]]);
      }
    }
  }
  return pairs;
}

// Timing for the "hold, then ease back" choreography after an answer lands.
const HOLD_MS = 2600;
const SETTLE_MS = 1800;

function now(): string {
  return new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function uniq(xs: string[]): string[] {
  return Array.from(new Set(xs));
}

function fmtScore(n: number | null): string {
  return n == null ? "—" : n.toFixed(2);
}

/** One line of the pipeline trace: a label and its outcome, in the same
 * question → plan → retrieve → rerank → evidence → conflict → version order
 * the agent itself actually runs in (see app/agent.py). */
function TraceLine({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <li className="flex gap-2 text-[0.7rem] leading-relaxed text-graphite">
      <span className="w-20 shrink-0 font-mono text-[0.62rem] uppercase tracking-cartouche text-graphite/70">
        {label}
      </span>
      <span className="text-ink">{children}</span>
    </li>
  );
}

/** Which citation (if any) an evidence chunk actually supports — the CLAIM
 * step of the CLAIM → CHUNK → DOCUMENT → VERSION → FRESHNESS → SCORES →
 * CONFLICT chain (Trust Layer Phase 6). `undefined` under MAX_TRUST's
 * non-cited evidence entries, which support no specific claim. */
function claimForChunk(resp: ChatResponse, chunkId: string): string | undefined {
  return resp.citations.find((c) => c.chunk_ids.includes(chunkId))?.claim;
}

/** Every conflict a chunk is one side of — a chunk can be `chunk_id_a` in one
 * pair and `chunk_id_b` in another, so this returns all matches, not just
 * the first. */
function conflictsForChunk(conflicts: Conflict[], chunkId: string): Conflict[] {
  return conflicts.filter((c) => c.chunk_id_a === chunkId || c.chunk_id_b === chunkId);
}

/**
 * "Why this answer?" — a two-part trace: first the pipeline itself (what the
 * agent actually did, in order: query planning → retrieval → reranking →
 * evidence selection → conflict check → version), then, per source, the full
 * CLAIM → SUPPORTING CHUNK → DOCUMENT → VERSION → FRESHNESS → DENSE/SPARSE/
 * RERANK SCORES → CONFLICT STATUS chain (Trust Layer Phase 6) — deliberately
 * never collapsed into one number, the reader judges each link themselves.
 */
function WhyThisAnswer({ resp, question }: { resp: ChatResponse; question: string }) {
  const [open, setOpen] = useState(false);
  const evidence = resp.evidence ?? [];
  if (evidence.length === 0) return null;
  const conflicts = resp.conflicts ?? [];

  const searchedQuery = resp.queries?.[0];
  const wasRewritten =
    !!searchedQuery && searchedQuery.trim().toLowerCase() !== question.trim().toLowerCase();
  const distinctDocs = uniq(resp.retrieved.map((r) => r.document_id)).length;
  const wasReranked = resp.retrieved.some((r) => r.rerank_score != null);
  const conflictsChecked = distinctDocs >= 2;
  const currentVersions = evidence.filter((e) => e.is_current_version).length;

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="marginalia text-[0.65rem] uppercase tracking-cartouche text-graphite hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter"
      >
        {open ? "▾" : "▸"} Why this answer?
      </button>
      {open ? (
        <div className="mt-2 flex flex-col gap-3">
          <ol className="flex flex-col gap-1 border-l border-graphite/25 pl-2">
            {wasRewritten ? (
              <TraceLine label="Query">Rewrote your question to &ldquo;{searchedQuery}&rdquo;</TraceLine>
            ) : null}
            <TraceLine label="Retrieve">
              {resp.retrieved.length} candidate{resp.retrieved.length === 1 ? "" : "s"} across{" "}
              {distinctDocs} document{distinctDocs === 1 ? "" : "s"}
            </TraceLine>
            {wasReranked ? (
              <TraceLine label="Rerank">Reordered candidates by relevance</TraceLine>
            ) : null}
            <TraceLine label="Evidence">
              {evidence.length} source{evidence.length === 1 ? "" : "s"}
              {resp.trust_mode === "MAX_TRUST" ? " traced (complete — every retrieved chunk)" : " selected for citation"}
            </TraceLine>
            {conflictsChecked ? (
              <TraceLine label="Conflicts">
                {conflicts.length > 0
                  ? `${conflicts.length} found — see "Sources disagree" above`
                  : "None detected"}
              </TraceLine>
            ) : null}
            <TraceLine label="Version">
              {currentVersions === evidence.length
                ? "All sources are the current version"
                : `${evidence.length - currentVersions} of ${evidence.length} source(s) from a superseded version`}
            </TraceLine>
          </ol>
          <ul className="flex flex-col gap-3">
            {evidence.map((e) => {
              const claim = claimForChunk(resp, e.chunk_id);
              const chunkConflicts = conflictsForChunk(conflicts, e.chunk_id);
              return (
                <li
                  key={e.chunk_id}
                  className={`border-l pl-2 text-[0.7rem] leading-relaxed text-graphite ${
                    chunkConflicts.length > 0 ? "border-signal-red/50" : "border-graphite/25"
                  }`}
                >
                  {e.is_cited === false ? (
                    <p className="marginalia text-[0.62rem] uppercase tracking-cartouche text-graphite/60">
                      retrieved, not cited
                    </p>
                  ) : null}
                  {claim ? <p className="italic text-ink">&ldquo;{claim}&rdquo;</p> : null}
                  <p className="text-ink">
                    {e.filename}
                    {e.page_num != null ? ` · page ${e.page_num}` : e.section ? ` · ${e.section}` : ""}
                  </p>
                  <p>{e.version_number != null ? `version ${e.version_number}` : "version unknown"}</p>
                  <p className={e.staleness > 0.5 ? "text-brass" : ""}>
                    {e.last_verified_at
                      ? `verified ${formatDate(e.last_verified_at)}`
                      : e.staleness > 0.5
                        ? "never verified — aging"
                        : "not yet verified"}
                  </p>
                  <p>
                    dense {fmtScore(e.dense_score)} · sparse {fmtScore(e.sparse_score)} · rerank{" "}
                    {fmtScore(e.rerank_score)}
                  </p>
                  <p className={chunkConflicts.length > 0 ? "font-medium text-signal-red" : ""}>
                    {chunkConflicts.length > 0
                      ? `conflict detected · confidence ${
                          chunkConflicts[0].confidence != null
                            ? `${Math.round(chunkConflicts[0].confidence * 100)}%`
                            : "—"
                        }`
                      : "no conflict detected"}
                  </p>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/** Thumbs up/down on one answer. Optimistic — the rating is local until the
 * request lands, and reverts if it fails, since a stale "thanks!" is worse
 * than a moment of lag. */
function FeedbackButtons({ messageId }: { messageId: string }) {
  const [rating, setRating] = useState<"up" | "down" | null>(null);
  const [pending, setPending] = useState(false);

  async function rate(next: "up" | "down") {
    if (pending) return;
    const prev = rating;
    setRating(next);
    setPending(true);
    try {
      await api.rateMessage(messageId, next);
    } catch {
      setRating(prev);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mt-3 flex items-center gap-2">
      <button
        type="button"
        onClick={() => rate("up")}
        disabled={pending}
        aria-pressed={rating === "up"}
        aria-label="This answer looks right"
        className={`rounded-sm border px-1.5 py-0.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter disabled:opacity-50 ${
          rating === "up"
            ? "border-verdigris bg-verdigris/15 text-verdigris"
            : "border-graphite/30 text-graphite hover:text-ink"
        }`}
      >
        ▲
      </button>
      <button
        type="button"
        onClick={() => rate("down")}
        disabled={pending}
        aria-pressed={rating === "down"}
        aria-label="This answer looks wrong"
        className={`rounded-sm border px-1.5 py-0.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter disabled:opacity-50 ${
          rating === "down"
            ? "border-brass bg-brass/15 text-brass"
            : "border-graphite/30 text-graphite hover:text-ink"
        }`}
      >
        ▼
      </button>
    </div>
  );
}

/** Trust Layer Phase 5: structured trust signals, not a single fabricated
 * percentage — every value here is read straight off `resp.trust_summary`,
 * itself computed server-side from real evidence (app/trust_summary.py).
 * Weak grounding renders as "Low"/"Unknown", never smoothed into a falsely
 * reassuring label. */
function TrustSummaryBlock({ resp }: { resp: ChatResponse }) {
  const t = resp.trust_summary;
  if (!t) return null;
  const rows: [string, string][] = [
    [
      "Citation coverage",
      t.citation_coverage != null ? `${Math.round(t.citation_coverage * 100)}%` : "—",
    ],
    ["Citation quality", t.citation_quality],
    ["Source freshness", t.source_freshness],
    ["Version", t.version],
    ["Conflicts", t.conflicts_detected > 0 ? `${t.conflicts_detected} detected` : "None detected"],
    ["Evidence completeness", t.evidence_completeness],
    ["Permission check", t.permission_check],
  ];
  const weak = (v: string) => v === "Low" || v === "Unknown";
  return (
    <div className="mt-3 border border-graphite/25 px-3 py-2">
      <p className="marginalia text-[0.65rem] uppercase tracking-cartouche text-graphite">Trust summary</p>
      <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between gap-2 text-[0.7rem]">
            <dt className="text-graphite">{label}</dt>
            <dd className={weak(value) ? "font-medium text-brass" : "text-ink"}>{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** Side-by-side conflicting claims (Trust Layer Phase 6) — never merged into
 * one blended statement. Falls back to the older topic/description-only
 * shape if `claim_a`/`claim_b` are absent (a cached pre-Phase-1 response). */
function ConflictsPanel({ conflicts }: { conflicts: Conflict[] }) {
  if (conflicts.length === 0) return null;
  return (
    <div className="mt-3 flex flex-col gap-3">
      {conflicts.map((c, i) => (
        <div key={i} className="border border-signal-red/50 bg-signal-red/5 px-3 py-2">
          <p className="marginalia text-[0.65rem] uppercase tracking-cartouche text-signal-red">
            Sources disagree — {c.topic}
          </p>
          {c.claim_a && c.claim_b ? (
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
              <div className="border-l-2 border-graphite/40 pl-2">
                <p className="marginalia text-[0.6rem] uppercase tracking-cartouche text-graphite">Source A</p>
                <p className="text-xs leading-relaxed text-ink">&ldquo;{c.claim_a}&rdquo;</p>
              </div>
              <div className="border-l-2 border-graphite/40 pl-2">
                <p className="marginalia text-[0.6rem] uppercase tracking-cartouche text-graphite">Source B</p>
                <p className="text-xs leading-relaxed text-ink">&ldquo;{c.claim_b}&rdquo;</p>
              </div>
            </div>
          ) : (
            <p className="mt-1 text-xs leading-relaxed text-ink">{c.description}</p>
          )}
          <p className="mt-2 text-[0.65rem] font-medium text-signal-red">
            Conflict detected · confidence {c.confidence != null ? `${Math.round(c.confidence * 100)}%` : "—"}
          </p>
        </div>
      ))}
    </div>
  );
}

function AnswerEntry({
  resp,
  question,
  onHoverDoc,
}: {
  resp: ChatResponse;
  question: string;
  onHoverDoc: (documentId: string | null) => void;
}) {
  const { order } = numberSources(resp);

  if (!resp.answerable) {
    return (
      <div className="border-l-2 border-graphite/40 pl-4">
        <p className="text-sm leading-relaxed text-ink">{resp.answer}</p>
        <p className="mt-2 text-xs text-graphite">
          No uploaded source supported an answer. Upload a relevant document, or rephrase the
          question to match what you&rsquo;ve mapped.
        </p>
      </div>
    );
  }

  return (
    <div className="atlas-fade-in border-l-2 border-graphite/40 pl-4">
      <p className="text-sm leading-relaxed text-ink">
        {renderAnswerWithCitations(resp, { onHoverDoc })}
      </p>
      {order.length > 0 ? (
        <div className="mt-3">
          <p className="marginalia text-[0.65rem] uppercase tracking-cartouche text-graphite">Sources</p>
          <ul className="mt-1 flex flex-col gap-1">
            {order.map((s) => (
              <li
                key={s.chunkId}
                className="marginalia flex gap-2 text-[0.7rem] text-graphite"
                onMouseEnter={() => onHoverDoc(s.chunk?.document_id ?? null)}
                onMouseLeave={() => onHoverDoc(null)}
              >
                <span className="rounded-sm bg-beacon/90 px-1 text-ink">[{s.index}]</span>
                <span>{s.chunk?.page_num != null ? `page ${s.chunk.page_num}` : "—"}</span>
                <span className="truncate">{s.chunkId}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <TrustSummaryBlock resp={resp} />
      <ConflictsPanel conflicts={resp.conflicts ?? []} />
      <WhyThisAnswer resp={resp} question={question} />
      {resp.message_id ? <FeedbackButtons messageId={resp.message_id} /> : null}
    </div>
  );
}

export function ChatView() {
  const capabilities = useCapabilities();
  const [docs, setDocs] = useState<DocumentOut[] | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [atlas, setAtlas] = useState<AtlasState>(IDLE);
  const [highlightedId, setHighlightedId] = useState<string | null>(null);
  const [atlasOpen, setAtlasOpen] = useState(true);
  // Desktop-only draggable split between the answer panel and the Living
  // Atlas — the atlas previously had a fixed 420px width, too cramped for
  // the 3D scene on some layouts and not adjustable at all. Persisted so a
  // resize sticks across reloads, same localStorage-preference pattern
  // lib/motion.ts already uses for "Atlas motion".
  const [atlasWidth, setAtlasWidth] = useState(() => {
    if (typeof window === "undefined") return 420;
    const stored = Number(window.localStorage.getItem("atlaskb.atlasWidth"));
    return Number.isFinite(stored) && stored >= 280 && stored <= 900 ? stored : 420;
  });
  const [isDesktop, setIsDesktop] = useState(false);
  const resizing = useRef<{ startX: number; startWidth: number } | null>(null);

  const endRef = useRef<HTMLDivElement>(null);
  const reqId = useRef(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)"); // Tailwind's `lg`
    const sync = () => setIsDesktop(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  const onResizeStart = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      resizing.current = { startX: e.clientX, startWidth: atlasWidth };
      const onMove = (ev: PointerEvent) => {
        if (!resizing.current) return;
        // The atlas pane sits to the right of the handle — dragging left
        // (negative delta) grows it, dragging right shrinks it.
        const delta = ev.clientX - resizing.current.startX;
        const next = Math.min(900, Math.max(280, resizing.current.startWidth - delta));
        setAtlasWidth(next);
      };
      const onUp = () => {
        resizing.current = null;
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        setAtlasWidth((w) => {
          window.localStorage.setItem("atlaskb.atlasWidth", String(w));
          return w;
        });
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    },
    [atlasWidth],
  );

  const { nodes, edges } = useMemo(
    () => layoutFromDocuments((docs ?? []).map((d) => ({ id: d.id, filename: d.filename }))),
    [docs],
  );

  useEffect(() => {
    api
      .listDocuments()
      .then(setDocs)
      .catch(() => setDocs([]));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [entries]);

  const clearTimers = useCallback(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  }, []);

  useEffect(() => () => clearTimers(), [clearTimers]);

  const scheduleSettle = useCallback((id: number) => {
    timers.current.push(
      setTimeout(() => {
        if (reqId.current === id) setAtlas((a) => ({ ...a, focus: false, phase: "settling" }));
      }, HOLD_MS),
    );
    timers.current.push(
      setTimeout(() => {
        if (reqId.current === id) setAtlas(IDLE);
      }, HOLD_MS + SETTLE_MS),
    );
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const text = question.trim();
    if (!text || pending) return;

    clearTimers();
    const id = ++reqId.current;
    const pid = crypto.randomUUID();
    setEntries((prev) => [
      ...prev,
      { kind: "question", id: crypto.randomUUID(), at: now(), text },
      { kind: "pending", id: pid },
    ]);
    setQuestion("");
    setPending(true);
    setHighlightedId(null);
    // Focus the (as yet unknown) cluster immediately so the camera starts easing.
    setAtlas({ activeIds: [], citedIds: [], staleIds: [], conflictPairs: [], focus: true, phase: "retrieving" });

    // /search returns retrieval-only results fast (no LLM) → drive the camera and
    // threads as soon as retrieval is known, before the answer is generated.
    api
      .search(text, 3)
      .then((res) => {
        if (reqId.current !== id) return;
        setAtlas((a) => ({ ...a, activeIds: uniq(res.results.map((c) => c.document_id)) }));
      })
      .catch(() => {});

    try {
      const resp = await api.chat(text, 3);
      const docByChunk = new Map(resp.retrieved.map((c) => [c.chunk_id, c.document_id] as const));
      const retrievedDocs = uniq(resp.retrieved.map((c) => c.document_id));
      const citedDocs = uniq(
        resp.citations
          .flatMap((c) => c.chunk_ids)
          .map((cid) => docByChunk.get(cid))
          .filter((x): x is string => !!x),
      );
      if (reqId.current === id) {
        setEntries((prev) =>
          prev.map((entry) =>
            entry.id === pid ? { kind: "answer", id: pid, at: now(), resp, question: text } : entry,
          ),
        );
        setAtlas({
          activeIds: retrievedDocs,
          citedIds: citedDocs,
          staleIds: staleDocIds(resp.evidence),
          conflictPairs: conflictDocPairs(resp.conflicts),
          focus: true,
          phase: "answered",
        });
        scheduleSettle(id);
      }
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "The answer service didn't respond. Check the backend is running and ask again.";
      if (reqId.current === id) {
        setEntries((prev) =>
          prev.map((entry) => (entry.id === pid ? { kind: "error", id: pid, at: now(), message } : entry)),
        );
        setAtlas(IDLE);
      }
    } finally {
      if (reqId.current === id) setPending(false);
    }
  }

  const hasNodes = nodes.length > 0;

  return (
    // Fill the shell's content area exactly (h-full) so the page itself never
    // scrolls — only the transcript does. h-full also gives the atlas pane a
    // real, full-height box to fill (a flex row would otherwise collapse to the
    // short panel's height).
    <div className="flex h-full flex-col lg:flex-row">
      {/* --- The Living Atlas (collapsible) or its 2D fallback. ---
          Phase 12: secondary explainability, not the default focus — the
          answer panel below carries `order-1` so Answer → Citations → Trust
          Summary → Conflicts → Evidence are always read (and, on desktop,
          laid out) before the atlas, without physically reordering this
          JSX. Atlas/2D-fallback/reduced-motion behavior is unchanged. */}
      {atlasOpen ? (
      <div
        className="relative order-2 h-[38vh] shrink-0 border-t border-graphite/25 lg:h-auto lg:flex-none lg:border-t-0 lg:border-l"
        style={isDesktop ? { width: atlasWidth } : undefined}
      >
        {/* Drag to resize (desktop only) — the atlas previously had a fixed
            420px width with no way to give the 3D scene more room. */}
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize the Living Atlas panel"
          tabIndex={0}
          onPointerDown={onResizeStart}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") setAtlasWidth((w) => Math.min(900, w + 20));
            if (e.key === "ArrowRight") setAtlasWidth((w) => Math.max(280, w - 20));
          }}
          className="absolute -left-1.5 top-0 z-20 hidden h-full w-3 cursor-col-resize touch-none items-center justify-center lg:flex focus-visible:outline-none"
        >
          <span aria-hidden className="h-10 w-0.5 rounded-full bg-graphite/40" />
        </div>
        <button
          type="button"
          onClick={() => setAtlasOpen(false)}
          className="absolute left-3 top-3 z-10 font-mono text-[0.65rem] uppercase tracking-cartouche text-graphite hover:text-parchment focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass"
        >
          ▾ collapse
        </button>
        {docs === null ? (
          <div className="flex h-full items-center justify-center">
            <ContourProgress size={40} label="Mapping your documents" />
          </div>
        ) : !hasNodes ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
            <p className="text-sm text-ink">Nothing mapped yet.</p>
            <p className="max-w-xs text-xs text-graphite">
              Upload a document to place it on the atlas, then ask a question to watch the route
              light up.
            </p>
          </div>
        ) : capabilities.functionalDegraded ? (
          <Atlas2DFallback
            nodes={nodes}
            edges={edges}
            activeIds={atlas.activeIds}
            citedIds={atlas.citedIds}
            highlightedId={highlightedId}
            focus={atlas.focus}
            reducedMotion={capabilities.reducedMotion}
            staleIds={atlas.staleIds}
            conflictPairs={atlas.conflictPairs}
          />
        ) : (
          // Decorative WebGL: the answer panel is the accessible source of truth,
          // so the canvas is hidden from assistive tech and the tab order. The
          // 2D fallback above stays exposed (role="img" with a label).
          <div aria-hidden="true" className="h-full w-full">
            <LivingAtlas
              mode="functional"
              nodes={nodes}
              edges={edges}
              activeIds={atlas.activeIds}
              citedIds={atlas.citedIds}
              highlightedId={highlightedId}
              focus={atlas.focus}
              reducedMotion={capabilities.reducedMotion}
              staleIds={atlas.staleIds}
              conflictPairs={atlas.conflictPairs}
            />
          </div>
        )}
        <span className="marginalia pointer-events-none absolute right-3 top-3 text-[0.65rem] uppercase tracking-cartouche text-graphite">
          Living Atlas{capabilities.functionalDegraded ? " · 2D" : ""}
        </span>
      </div>
      ) : (
        <button
          type="button"
          onClick={() => setAtlasOpen(true)}
          className="order-2 flex shrink-0 items-center gap-2 border-t border-graphite/25 px-4 py-2 font-mono text-[0.65rem] uppercase tracking-cartouche text-graphite hover:text-parchment focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass lg:h-auto lg:w-10 lg:flex-col lg:justify-center lg:border-t-0 lg:border-l"
        >
          <span aria-hidden>▸</span>
          <span className="lg:[writing-mode:vertical-rl]">Living Atlas</span>
        </button>
      )}

      {/* --- The answer panel: Answer → Citations → Trust Summary →
          Conflicts → Evidence (Trust Layer Phase 12) — primary, always
          fully functional, and now `order-1` so it's read/laid out before
          the atlas in both the mobile stack and the desktop row. --- */}
      <aside className="order-1 flex min-h-0 w-full flex-1 flex-col">
        <div
          role="log"
          aria-label="Question and answer log"
          className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6"
        >
          {entries.length === 0 ? (
            <div className="flex h-full flex-col justify-center gap-3">
              <h1 className="font-display text-2xl font-medium text-ink">Ask your atlas</h1>
              <p className="max-w-sm text-sm text-graphite">
                Ask a question and AtlasKB surveys the map — the camera flies to the documents that
                answer you, and every claim is cited. Hover a citation to find its place on the map.
              </p>
            </div>
          ) : (
            <ol className="flex flex-col gap-6">
              {entries.map((entry) => {
                if (entry.kind === "question") {
                  // User message: right-aligned, deep-chart with a brass hairline.
                  return (
                    <li key={entry.id} className="chat-enter flex flex-col items-end gap-1">
                      <span className="marginalia text-[0.7rem]">{entry.at} ▸ you asked</span>
                      <p className="max-w-[85%] rounded-sm border border-brass/40 bg-deep-chart px-3 py-2 text-sm text-parchment">
                        {entry.text}
                      </p>
                    </li>
                  );
                }
                if (entry.kind === "pending") {
                  return (
                    <li key={entry.id} aria-live="polite" className="chat-enter flex items-center gap-2 pl-4">
                      <ContourProgress size={18} label="Triangulating an answer" />
                      <span className="marginalia text-xs">triangulating…</span>
                    </li>
                  );
                }
                if (entry.kind === "error") {
                  return (
                    <li key={entry.id} className="chat-enter flex flex-col gap-1">
                      <span className="marginalia text-[0.7rem]">{entry.at} · could not answer</span>
                      <p role="alert" className="border border-signal-red/60 bg-signal-red/10 px-3 py-2 text-sm text-parchment">
                        {entry.message}
                      </p>
                    </li>
                  );
                }
                // Assistant message: left-aligned, parchment.
                return (
                  <li key={entry.id} className="chat-enter flex flex-col items-start gap-1">
                    <span className="marginalia text-[0.7rem]">{entry.at} · answer</span>
                    <div className="max-w-[92%]">
                      <AnswerEntry resp={entry.resp} question={entry.question} onHoverDoc={setHighlightedId} />
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
          <div ref={endRef} />
        </div>

        {/* The ruled input — "write on the chart". */}
        <form onSubmit={onSubmit} className="border-t border-graphite/25 p-4 sm:px-6">
          <label htmlFor="chat-input" className="sr-only">
            Ask a question
          </label>
          <div className="relative">
            <div className="flex items-end gap-3 border-b border-graphite/50 focus-within:border-ink">
              <textarea
                id="chat-input"
                rows={1}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    onSubmit(e as unknown as FormEvent);
                  }
                }}
                placeholder="Ask a question about your documents…"
                className="max-h-40 min-h-[2.5rem] flex-1 resize-none bg-transparent py-2 text-sm text-ink placeholder:text-graphite/60 focus-visible:outline-none"
              />
              <button
                type="submit"
                disabled={pending || question.trim().length === 0}
                className="mb-1 border border-ink bg-ink px-4 py-1.5 font-mono text-xs uppercase tracking-cartouche text-linen transition-colors hover:border-graphite hover:bg-graphite focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter focus-visible:ring-offset-2 focus-visible:ring-offset-linen disabled:cursor-not-allowed disabled:opacity-50"
              >
                Ask
              </button>
            </div>
            {pending ? (
              <div className="absolute inset-x-0 bottom-0 h-0.5 overflow-hidden" aria-hidden>
                <div className="survey-line h-full w-1/4 bg-beacon" />
              </div>
            ) : null}
          </div>
          <p className="marginalia mt-2 text-[0.65rem] text-graphite">
            Enter to ask · Shift+Enter for a new line
          </p>
        </form>
      </aside>
    </div>
  );
}
