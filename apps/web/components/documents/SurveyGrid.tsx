"use client";

import { useEffect, useState } from "react";

// Contour-line "survey" grid with a sweeping scan line, shown while a document is
// being ingested. Tied to the real processing status. The three passes below
// (parse → chunk → embed) mirror the ingestion pipeline; they cycle on a timer
// because the backend does not yet emit per-stage progress events — an honest
// indeterminate indicator, not a fake precise bar.
const PASSES = ["Parsing", "Chunking", "Embedding"] as const;

export function SurveyGrid({ label = "Surveying" }: { label?: string }) {
  const [pass, setPass] = useState(0);
  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;
    const t = setInterval(() => setPass((p) => (p + 1) % PASSES.length), 1400);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="flex items-center gap-4">
      <svg width="88" height="64" viewBox="0 0 88 64" aria-hidden className="shrink-0">
        {/* contour lines (the flat "document" being surveyed) */}
        {[10, 22, 34, 46].map((y) => (
          <path
            key={y}
            d={`M4 ${y} Q 22 ${y - 6}, 44 ${y} T 84 ${y}`}
            fill="none"
            stroke="#515C63"
            strokeWidth="1"
            opacity={0.5}
          />
        ))}
        {/* sweeping survey line */}
        <line x1="0" y1="0" x2="0" y2="64" stroke="#B08D4F" strokeWidth="1.5">
          <animate
            attributeName="x1"
            from="6"
            to="82"
            dur="1.4s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="x2"
            from="6"
            to="82"
            dur="1.4s"
            repeatCount="indefinite"
          />
        </line>
      </svg>
      <div>
        <p className="font-mono text-xs uppercase tracking-cartouche text-graphite">{label}</p>
        <p className="mt-0.5 text-sm text-ink">{PASSES[pass]}…</p>
      </div>
    </div>
  );
}
