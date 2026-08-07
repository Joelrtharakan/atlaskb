"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { Atlas2DFallback } from "@/components/living-atlas/Atlas2DFallback";
import { layoutFromDocuments } from "@/components/living-atlas/layout";
import { useCapabilities } from "@/components/living-atlas/use-capabilities";
import { ContourProgress } from "@/components/ui/ContourProgress";
import { ApiError, api } from "@/lib/api";
import type { ChatResponse, DocumentOut } from "@/lib/types";

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
  | { kind: "answer"; id: string; at: string; resp: ChatResponse }
  | { kind: "error"; id: string; at: string; message: string };

type AtlasState = {
  activeIds: string[];
  citedIds: string[];
  focus: boolean;
  phase: "idle" | "retrieving" | "answered" | "settling";
};

const IDLE: AtlasState = { activeIds: [], citedIds: [], focus: false, phase: "idle" };

// Timing for the "hold, then ease back" choreography after an answer lands.
const HOLD_MS = 2600;
const SETTLE_MS = 1800;

function now(): string {
  return new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function uniq(xs: string[]): string[] {
  return Array.from(new Set(xs));
}

function AnswerEntry({
  resp,
  onHoverDoc,
}: {
  resp: ChatResponse;
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

  const endRef = useRef<HTMLDivElement>(null);
  const reqId = useRef(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

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
    setAtlas({ activeIds: [], citedIds: [], focus: true, phase: "retrieving" });

    // /search returns retrieval-only results fast (no LLM) → drive the camera and
    // threads as soon as retrieval is known, before the answer is generated.
    api
      .search(text, 8)
      .then((res) => {
        if (reqId.current !== id) return;
        setAtlas((a) => ({ ...a, activeIds: uniq(res.results.map((c) => c.document_id)) }));
      })
      .catch(() => {});

    try {
      const resp = await api.chat(text, 8);
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
          prev.map((entry) => (entry.id === pid ? { kind: "answer", id: pid, at: now(), resp } : entry)),
        );
        setAtlas({
          activeIds: retrievedDocs,
          citedIds: citedDocs,
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
    <div className="flex h-full flex-col lg:flex-row">
      {/* --- The Living Atlas (or its 2D fallback). --- */}
      <div className="relative min-h-[38vh] flex-1 border-b border-graphite/25 lg:min-h-0 lg:border-b-0 lg:border-r">
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
            />
          </div>
        )}
        <span className="marginalia pointer-events-none absolute right-3 top-3 text-[0.65rem] uppercase tracking-cartouche text-graphite">
          Living Atlas{capabilities.functionalDegraded ? " · 2D" : ""}
        </span>
      </div>

      {/* --- The answer panel (always fully functional). --- */}
      <aside className="flex min-h-0 w-full flex-col lg:w-[420px]">
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
                  return (
                    <li key={entry.id} className="flex flex-col gap-1">
                      <span className="marginalia text-[0.7rem]">{entry.at} ▸ you asked</span>
                      <p className="text-sm font-medium text-ink">{entry.text}</p>
                    </li>
                  );
                }
                if (entry.kind === "pending") {
                  return (
                    <li key={entry.id} aria-live="polite" className="flex items-center gap-2 pl-4">
                      <ContourProgress size={18} label="Triangulating an answer" />
                      <span className="marginalia text-xs">triangulating…</span>
                    </li>
                  );
                }
                if (entry.kind === "error") {
                  return (
                    <li key={entry.id} className="flex flex-col gap-1">
                      <span className="marginalia text-[0.7rem]">{entry.at} · could not answer</span>
                      <p role="alert" className="border border-ink bg-ink/5 px-3 py-2 text-sm text-ink">
                        {entry.message}
                      </p>
                    </li>
                  );
                }
                return (
                  <li key={entry.id} className="flex flex-col gap-1">
                    <span className="marginalia text-[0.7rem]">{entry.at} · answer</span>
                    <AnswerEntry resp={entry.resp} onHoverDoc={setHighlightedId} />
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
