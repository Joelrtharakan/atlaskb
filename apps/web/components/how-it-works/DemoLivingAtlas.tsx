"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";

import { Atlas2DFallback } from "@/components/living-atlas/Atlas2DFallback";
import { layoutFromDocuments } from "@/components/living-atlas/layout";
import { useCapabilities } from "@/components/living-atlas/use-capabilities";
import { CitationMarker } from "@/components/ui/CitationMarker";
import type { ScoredChunk } from "@/lib/types";

// The Three.js scene is loaded on demand, same as ChatView does — this
// section shouldn't cost anything on routes that never render it.
const LivingAtlas = dynamic(() => import("@/components/living-atlas/LivingAtlas"), { ssr: false });

// A small, fixed demo corpus — not fetched from anywhere, doesn't need a
// backend or auth session, but laid out with the exact same
// `layoutFromDocuments` function real tenant documents go through.
const DEMO_DOCS = [
  { id: "demo-1", filename: "security_and_data_policy.pdf", title: "Security & Data Policy" },
  { id: "demo-2", filename: "q3_2024_allhands_notes.pdf", title: "Q3 2024 All-Hands Notes" },
  { id: "demo-3", filename: "falcon_product_spec.pdf", title: "Falcon Product Spec" },
];
const { nodes: DEMO_NODES, edges: DEMO_EDGES } = layoutFromDocuments(DEMO_DOCS);

const DEMO_CHUNK: ScoredChunk = {
  chunk_id: "demo-chunk-1",
  document_id: "demo-1",
  version_id: "demo-1-v1",
  text: "Customer data is retained for 90 days after account closure, after which it is permanently purged from primary and backup storage.",
  page_num: 4,
  section: null,
  score: 0.91,
  dense_score: 0.88,
  sparse_score: 0.74,
  rerank_score: 0.93,
};
const DEMO_QUESTION = "What's our data retention policy after a customer closes their account?";

type Phase = "idle" | "retrieving" | "answered";

/**
 * Section 1's credibility anchor: the actual LivingAtlas component (same one
 * `/chat` renders), fed a small fixed demo corpus instead of a live backend
 * response. Not a mockup — literally the production component, in
 * `mode="functional"`, driven by the same activeIds/citedIds/focus props
 * ChatView.tsx uses. Falls back to the real Atlas2DFallback (also production
 * code, not a recreation) under reduced-motion/low-power/no-WebGL.
 */
export function DemoLivingAtlas() {
  const { reducedMotion, lowPower, webgl } = useCapabilities();
  const hostRef = useRef<HTMLDivElement>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [hovering, setHovering] = useState(false);

  // useReducedMotion() resolves asynchronously (starts false, updates in its
  // own effect after mount) — a lazy useState initializer keyed on it would
  // catch that transient false and never revisit it. Syncing in an effect
  // instead means this still lands on "answered" once the real value arrives.
  useEffect(() => {
    if (reducedMotion) setPhase("answered");
  }, [reducedMotion]);

  useEffect(() => {
    if (reducedMotion) return;
    const el = hostRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting || phase !== "idle") return;
        setPhase("retrieving");
        const t = setTimeout(() => setPhase("answered"), 1400);
        return () => clearTimeout(t);
      },
      { threshold: 0.5 },
    );
    io.observe(el);
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reducedMotion]);

  const activeIds = phase === "idle" ? [] : ["demo-1"];
  const citedIds = phase === "answered" ? ["demo-1"] : [];
  const focus = phase !== "idle";
  const highlightedId = hovering ? "demo-1" : null;
  const useFallback = lowPower || !webgl;

  return (
    <div>
      <div
        ref={hostRef}
        className="relative h-[320px] w-full overflow-hidden rounded-sm border border-graphite/20 bg-chart-navy sm:h-[380px]"
      >
        {useFallback ? (
          <Atlas2DFallback
            nodes={DEMO_NODES}
            edges={DEMO_EDGES}
            activeIds={activeIds}
            citedIds={citedIds}
            highlightedId={highlightedId}
            focus={focus}
            reducedMotion={reducedMotion}
          />
        ) : (
          <LivingAtlas
            mode="functional"
            nodes={DEMO_NODES}
            edges={DEMO_EDGES}
            activeIds={activeIds}
            citedIds={citedIds}
            highlightedId={highlightedId}
            focus={focus}
            reducedMotion={reducedMotion}
          />
        )}
      </div>
      <p className="mt-3 font-mono text-[0.65rem] uppercase tracking-cartouche text-verdigris">
        This is the actual Living Atlas component — not a recreation.
      </p>
      <div className="mt-4 min-h-[4.5rem]">
        <p className="text-sm text-parchment/60">{DEMO_QUESTION}</p>
        {phase === "answered" && (
          <p className="mt-1.5 text-sm leading-relaxed text-parchment/85">
            Customer data is retained for 90 days after account closure.
            <CitationMarker index={1} chunk={DEMO_CHUNK} onHoverChange={setHovering} />
          </p>
        )}
      </div>
    </div>
  );
}
