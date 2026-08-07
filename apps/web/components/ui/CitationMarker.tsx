"use client";

import { useId, useState } from "react";

import type { ScoredChunk } from "@/lib/types";

// Inline citation marker: a beacon chip [n] (the reserved "a source is live"
// color) that reveals its source chunk — text plus page — on hover, on keyboard
// focus, and on click (which pins it open). Fully operable by keyboard.

export function CitationMarker({ index, chunk }: { index: number; chunk: ScoredChunk | undefined }) {
  const [pinned, setPinned] = useState(false);
  const popId = useId();

  const location =
    chunk?.page_num != null
      ? `page ${chunk.page_num}`
      : chunk?.section
        ? chunk.section
        : "source";

  return (
    <span className="group relative inline-block align-baseline">
      <button
        type="button"
        aria-expanded={pinned}
        aria-controls={popId}
        onClick={() => setPinned((p) => !p)}
        className={
          "mx-0.5 inline-flex items-center rounded-sm bg-beacon/90 px-1.5 font-mono text-[0.7rem] " +
          "font-medium text-ink transition-colors hover:bg-beacon " +
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink " +
          "focus-visible:ring-offset-1 focus-visible:ring-offset-linen"
        }
      >
        <span className="sr-only">Citation {index}, </span>[{index}]
      </button>

      <span
        id={popId}
        role="tooltip"
        className={
          "absolute bottom-full left-0 z-20 mb-1 w-72 max-w-[80vw] " +
          "border border-graphite/50 bg-linen p-3 text-left shadow-sm " +
          "group-hover:block group-focus-within:block " +
          (pinned ? "block" : "hidden")
        }
      >
        <span className="marginalia mb-1 flex items-center justify-between text-[0.7rem]">
          <span className="uppercase tracking-cartouche text-beacon">source [{index}]</span>
          <span>{location}</span>
        </span>
        {chunk ? (
          <>
            <span className="block text-xs leading-relaxed text-ink">{chunk.text}</span>
            <span className="marginalia mt-2 block truncate text-[0.65rem] text-graphite">
              {chunk.chunk_id}
            </span>
          </>
        ) : (
          <span className="block text-xs text-graphite">
            This source is no longer available. Re-run the question to refresh its citations.
          </span>
        )}
      </span>
    </span>
  );
}
