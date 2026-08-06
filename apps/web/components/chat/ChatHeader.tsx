"use client";

import { useRetrieval, type RetrievalPhase } from "./retrieval";

const PHASE_LABEL: Record<RetrievalPhase, string> = {
  idle: "idle",
  triangulating: "triangulating…",
  plotting: "plotting route…",
  answering: "drafting…",
  complete: "idle",
};

/** Top strip — wordmark, tenant, live status + token meter (mono marginalia). */
export default function ChatHeader() {
  const { phase, totalTokens } = useRetrieval();

  return (
    <header className="flex items-center justify-between border-b border-graphite/25 px-6 py-3">
      <div className="flex items-center gap-3">
        <span aria-hidden className="text-pewter">
          ◈
        </span>
        <span className="font-mono text-sm uppercase tracking-cartouche text-ink">AtlasKB</span>
        <span aria-hidden className="text-graphite/40">
          ·
        </span>
        <span className="font-mono text-sm text-graphite">acme-corp</span>
      </div>
      <div className="marginalia flex items-center gap-4 text-[0.7rem]">
        <span className="text-pewter">{PHASE_LABEL[phase]}</span>
        <span>tokens {totalTokens.toLocaleString("en-US")}</span>
      </div>
    </header>
  );
}
