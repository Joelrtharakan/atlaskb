"use client";

import { useEffect, useRef } from "react";

import { PLACEHOLDER_DOCUMENTS } from "@/components/living-atlas/documents";
import { useRetrieval, type JournalEntry } from "./retrieval";

function timestamp(d: Date): string {
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function docTitle(id: string): string {
  return PLACEHOLDER_DOCUMENTS.find((d) => d.id === id)?.title ?? id;
}

const PHASE_STATUS: Record<JournalEntry["phase"], string> = {
  triangulating: "triangulating…",
  plotting: "plotting route…",
  answering: "drafting…",
  complete: "",
  idle: "",
};

/** One log entry — question, streamed answer, beacon citations, mono margin. */
function Entry({ entry }: { entry: JournalEntry }) {
  const status = PHASE_STATUS[entry.phase];
  const answering = entry.phase !== "complete";

  return (
    <article className="border-t border-graphite/20 py-6 first:border-t-0">
      <div className="flex gap-3">
        <span className="marginalia shrink-0 pt-1 text-[0.7rem]">{timestamp(entry.askedAt)}</span>
        <div className="min-w-0 flex-1">
          <p className="flex items-baseline gap-2 text-ink">
            <span aria-hidden className="text-pewter">
              ▸
            </span>
            <span className="font-medium">{entry.question}</span>
          </p>

          {status && <p className="marginalia mt-2 text-[0.7rem] text-pewter">{status}</p>}

          {entry.answer && (
            <div className="mt-3 max-w-prose text-[0.95rem] leading-relaxed text-graphite">
              <p>
                {entry.answer}
                {answering && <span className="ml-0.5 animate-pulse text-pewter">▍</span>}
              </p>

              {entry.citations.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {entry.citations.map((c) => (
                    <span
                      key={c.chunkId}
                      title={docTitle(c.docId)}
                      // Beacon: reserved for active citations.
                      className="inline-flex items-center gap-1 rounded-sm border border-beacon/50 bg-beacon/10 px-1.5 py-0.5 font-mono text-[0.7rem] text-ink"
                    >
                      <span aria-hidden className="text-beacon">
                        ◍
                      </span>
                      {c.chunkId}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {entry.phase === "complete" && (
            <p className="marginalia mt-3 flex flex-wrap gap-x-3 gap-y-1 text-[0.7rem]">
              <span>{entry.citations[0]?.chunkId ?? "—"}</span>
              <span aria-hidden>·</span>
              <span>${entry.costUsd.toFixed(4)}</span>
              <span aria-hidden>·</span>
              <span>{entry.latencyMs ?? "—"} ms</span>
              <span aria-hidden>·</span>
              <span>{entry.citations.length} sources</span>
            </p>
          )}
        </div>
      </div>
    </article>
  );
}

export default function FieldJournal() {
  const { entries } = useRetrieval();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [entries]);

  return (
    <div className="flex h-full flex-col overflow-y-auto px-6 py-4">
      {entries.length === 0 ? (
        <div className="marginalia m-auto max-w-xs text-center text-[0.8rem] leading-relaxed text-pewter">
          Field journal empty. Ask a question to survey the atlas — cited sources light as beacons,
          their route drawn in meridian.
        </div>
      ) : (
        <>
          {entries.map((entry) => (
            <Entry key={entry.id} entry={entry} />
          ))}
          <div ref={endRef} />
        </>
      )}
    </div>
  );
}
