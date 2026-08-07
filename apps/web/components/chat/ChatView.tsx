"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";

import { ContourProgress } from "@/components/ui/ContourProgress";
import { ApiError, api } from "@/lib/api";
import type { ChatResponse } from "@/lib/types";

import { numberSources, renderAnswerWithCitations } from "./citations";

type Entry =
  | { kind: "question"; id: string; at: string; text: string }
  | { kind: "pending"; id: string }
  | { kind: "answer"; id: string; at: string; resp: ChatResponse }
  | { kind: "error"; id: string; at: string; message: string };

function now(): string {
  return new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function AnswerEntry({ resp }: { resp: ChatResponse }) {
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
    <div className="border-l-2 border-graphite/40 pl-4">
      <p className="text-sm leading-relaxed text-ink">{renderAnswerWithCitations(resp)}</p>

      {order.length > 0 ? (
        <div className="mt-3">
          <p className="marginalia text-[0.65rem] uppercase tracking-cartouche text-pewter">
            Sources
          </p>
          <ul className="mt-1 flex flex-col gap-1">
            {order.map((s) => (
              <li key={s.chunkId} className="marginalia flex gap-2 text-[0.7rem] text-graphite">
                <span className="text-beacon">[{s.index}]</span>
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
  const [entries, setEntries] = useState<Entry[]>([]);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [entries]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const text = question.trim();
    if (!text || pending) return;

    const qid = crypto.randomUUID();
    const pid = crypto.randomUUID();
    setEntries((prev) => [
      ...prev,
      { kind: "question", id: qid, at: now(), text },
      { kind: "pending", id: pid },
    ]);
    setQuestion("");
    setPending(true);

    try {
      const resp = await api.chat(text);
      setEntries((prev) =>
        prev.map((entry) =>
          entry.id === pid ? { kind: "answer", id: pid, at: now(), resp } : entry,
        ),
      );
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "The answer service didn't respond. Check the backend is running and ask again.";
      setEntries((prev) =>
        prev.map((entry) =>
          entry.id === pid ? { kind: "error", id: pid, at: now(), message } : entry,
        ),
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col">
      {/* Transcript — the field journal. */}
      <div role="log" aria-label="Question and answer log" className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-8">
        {entries.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <h1 className="font-display text-3xl font-medium text-ink">Ask your atlas</h1>
            <p className="max-w-sm text-sm text-graphite">
              No routes plotted yet — ask a question and AtlasKB will answer from the documents
              you&rsquo;ve mapped, citing every source.
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
                  <AnswerEntry resp={entry.resp} />
                </li>
              );
            })}
          </ol>
        )}
        <div ref={endRef} />
      </div>

      {/* The ruled input — "write on the chart". */}
      <form onSubmit={onSubmit} className="border-t border-graphite/25 p-4 sm:px-8">
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
              className="mb-1 border border-ink bg-ink px-4 py-1.5 font-mono text-xs uppercase tracking-cartouche text-linen transition-colors hover:bg-graphite hover:border-graphite disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter focus-visible:ring-offset-2 focus-visible:ring-offset-linen"
            >
              Ask
            </button>
          </div>
          {/* Traveling beacon underline = retrieval in progress (reserved color). */}
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
    </div>
  );
}
