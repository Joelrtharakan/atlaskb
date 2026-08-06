"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { PLACEHOLDER_DOCUMENTS, documentIndex } from "@/components/living-atlas/documents";
import type { AtlasState } from "@/components/living-atlas/LivingAtlas";

/**
 * MOCK retrieval orchestration.
 *
 * This is the seam where real API events (SSE/WebSocket) will later drive the
 * transcript and the Living Atlas. For now a scripted timeline emits the same
 * shape of events so the beacon/meridian choreography is real and viewable:
 * triangulate → ignite nodes → plot route → stream answer → settle.
 *
 * Replace `runMockRetrieval` with a subscription to the API's retrieval stream;
 * the reducer-ish state transitions below stay the same.
 */

export type RetrievalPhase = "idle" | "triangulating" | "plotting" | "answering" | "complete";

export interface Citation {
  docId: string;
  chunkId: string;
}

export interface JournalEntry {
  id: string;
  question: string;
  askedAt: Date;
  answer: string;
  citations: Citation[];
  costUsd: number;
  latencyMs: number | null;
  phase: RetrievalPhase;
}

interface RetrievalContextValue {
  entries: JournalEntry[];
  phase: RetrievalPhase;
  atlas: AtlasState;
  totalTokens: number;
  busy: boolean;
  ask: (question: string) => void;
}

const RetrievalContext = createContext<RetrievalContextValue | null>(null);

const ANSWER = [
  "This is a scaffold response.",
  "Retrieval is mocked in this phase, but the choreography is real:",
  "each source the agent consults is lit as a beacon on the atlas,",
  "and the route between co-retrieved documents is drawn in meridian.",
  "Wiring these threads to live retrieval events is the next phase.",
].join(" ");

/** Tiny string hash so the same question always surveys the same territory. */
function hashString(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function pickRetrievedDocs(question: string): Citation[] {
  const seed = hashString(question.toLowerCase().trim() || "atlas");
  const count = 3 + (seed % 2); // 3–4 sources
  const chosen: number[] = [];
  let cursor = seed;
  while (chosen.length < count) {
    cursor = (cursor * 1103515245 + 12345) >>> 0;
    const idx = cursor % PLACEHOLDER_DOCUMENTS.length;
    if (!chosen.includes(idx)) chosen.push(idx);
  }
  return chosen.map((idx, k) => {
    const doc = PLACEHOLDER_DOCUMENTS[idx];
    const hex = ((seed >> (k * 3)) & 0xffff).toString(16).padStart(4, "0");
    const num = ((cursor >> (k * 4)) & 0xfff).toString().padStart(4, "0");
    return { docId: doc.id, chunkId: `${hex}-${num}` };
  });
}

export function RetrievalProvider({ children }: { children: React.ReactNode }) {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [phase, setPhase] = useState<RetrievalPhase>("idle");
  const [atlas, setAtlas] = useState<AtlasState>({ activeNodes: [], route: [], focus: false });
  const [totalTokens, setTotalTokens] = useState(0);

  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const clearTimers = useCallback(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  }, []);
  useEffect(() => clearTimers, [clearTimers]);

  const busy = phase !== "idle" && phase !== "complete";

  const ask = useCallback(
    (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || busy) return;
      clearTimers();

      const id = `q_${Date.now()}`;
      const askedAt = new Date();
      const cites = pickRetrievedDocs(trimmed);
      const nodeIdx = cites.map((c) => documentIndex(c.docId)).filter((i) => i >= 0);

      setEntries((prev) => [
        ...prev,
        {
          id,
          question: trimmed,
          askedAt,
          answer: "",
          citations: [],
          costUsd: 0,
          latencyMs: null,
          phase: "triangulating",
        },
      ]);
      setPhase("triangulating");
      setAtlas({ activeNodes: [], route: [], focus: true });

      const at = (ms: number, fn: () => void) => timers.current.push(setTimeout(fn, ms));
      const patch = (p: Partial<JournalEntry>) =>
        setEntries((prev) => prev.map((e) => (e.id === id ? { ...e, ...p } : e)));

      // Nodes ignite one by one.
      nodeIdx.forEach((idx, k) => {
        at(400 + k * 220, () => {
          setAtlas((s) => ({ ...s, activeNodes: [...s.activeNodes, idx], focus: true }));
          if (k === 0) {
            setPhase("plotting");
            patch({ phase: "plotting" });
          }
        });
      });

      // Route (meridian) plots once nodes are lit.
      const litAt = 400 + nodeIdx.length * 220;
      at(litAt + 150, () => setAtlas((s) => ({ ...s, route: nodeIdx })));

      // Answer streams; citations reveal progressively.
      const words = ANSWER.split(" ");
      const answerStart = litAt + 450;
      at(answerStart, () => {
        setPhase("answering");
        patch({ phase: "answering" });
      });
      words.forEach((_, i) => {
        at(answerStart + i * 45, () => {
          const shown = words.slice(0, i + 1).join(" ");
          const revealed = Math.min(
            cites.length,
            Math.floor(((i + 1) / words.length) * cites.length),
          );
          patch({
            answer: shown,
            citations: cites.slice(0, revealed),
            costUsd: (i + 1) * 0.00021,
          });
          setTotalTokens((t) => t + 2);
        });
      });

      // Complete + settle.
      const endAt = answerStart + words.length * 45;
      at(endAt, () => {
        setPhase("complete");
        patch({
          phase: "complete",
          citations: cites,
          latencyMs: Date.now() - askedAt.getTime(),
          costUsd: words.length * 0.00021,
        });
      });
      at(endAt + 1300, () => {
        setAtlas({ activeNodes: [], route: [], focus: false });
        setPhase("idle");
      });
    },
    [busy, clearTimers],
  );

  const value = useMemo(
    () => ({ entries, phase, atlas, totalTokens, busy, ask }),
    [entries, phase, atlas, totalTokens, busy, ask],
  );

  return <RetrievalContext.Provider value={value}>{children}</RetrievalContext.Provider>;
}

export function useRetrieval(): RetrievalContextValue {
  const ctx = useContext(RetrievalContext);
  if (!ctx) throw new Error("useRetrieval must be used within a RetrievalProvider");
  return ctx;
}
