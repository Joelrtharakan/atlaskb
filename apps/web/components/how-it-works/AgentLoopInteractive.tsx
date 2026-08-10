"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";

import { useReducedMotion } from "@/components/living-atlas/use-capabilities";
import { AGENT_MAX_ITERATIONS, AGENT_NODES } from "@/lib/how-it-works-content";

type NodeId = "plan" | "retrieve" | "assess" | "generate";
const SEQUENCE: NodeId[] = ["plan", "retrieve", "assess"];
const HEADING_DEG: Record<NodeId, number> = { plan: 0, retrieve: 90, assess: 180, generate: 270 };
const STEP_MS = 550;

/**
 * Section 4, made operable instead of just illustrated: the visitor plays
 * the agent's own sufficiency call. "Insufficient" replays plan → retrieve →
 * assess and increments a real, capped iteration counter — the actual
 * configured bound (AGENT_MAX_ITERATIONS), not a number picked for the demo.
 * "Sufficient" jumps straight to generate. Optionally reports state up so
 * the pinned background scene's compass can move in sync with the clicks.
 */
export function AgentLoopInteractive({
  onStateChange,
}: {
  onStateChange?: (headingDeg: number, activeIndex: number) => void;
}) {
  const reducedMotion = useReducedMotion();
  const hostRef = useRef<HTMLDivElement>(null);
  const [started, setStarted] = useState(false);
  const [iteration, setIteration] = useState(1);
  const [node, setNode] = useState<NodeId>("plan");
  const [playing, setPlaying] = useState(false);
  const [done, setDone] = useState(false);
  const [boundReached, setBoundReached] = useState(false);

  const report = (n: NodeId) => {
    const idx = SEQUENCE.indexOf(n) >= 0 ? SEQUENCE.indexOf(n) : 3;
    onStateChange?.(HEADING_DEG[n], idx);
  };

  // See DemoLivingAtlas's comment on the same pattern: useReducedMotion()
  // resolves asynchronously, so this has to be synced in an effect rather
  // than read once via a lazy useState initializer.
  useEffect(() => {
    if (!reducedMotion) return;
    setStarted(true);
    setNode("assess");
    report("assess");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reducedMotion]);

  const playSequence = (onFinish: () => void) => {
    // Reduced motion: clicking is a deliberate action, not ambient motion,
    // so it can stay interactive — it just jumps straight to the result
    // instead of animating through the intermediate steps.
    if (reducedMotion) {
      const last = SEQUENCE[SEQUENCE.length - 1];
      setNode(last);
      report(last);
      onFinish();
      return;
    }
    setPlaying(true);
    let i = 0;
    const step = () => {
      setNode(SEQUENCE[i]);
      report(SEQUENCE[i]);
      i++;
      if (i < SEQUENCE.length) setTimeout(step, STEP_MS);
      else {
        setPlaying(false);
        onFinish();
      }
    };
    step();
  };

  // Auto-play the first pass once this section actually scrolls into view —
  // not on mount, which would burn the animation off-screen.
  useEffect(() => {
    if (reducedMotion || started) return;
    const el = hostRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setStarted(true);
          io.disconnect();
          playSequence(() => {});
        }
      },
      { threshold: 0.4 },
    );
    io.observe(el);
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reducedMotion, started]);

  const handleInsufficient = () => {
    if (playing || done) return;
    if (iteration >= AGENT_MAX_ITERATIONS) {
      setBoundReached(true);
      setDone(true);
      setNode("generate");
      report("generate");
      return;
    }
    setIteration((n) => n + 1);
    playSequence(() => {});
  };

  const handleSufficient = () => {
    if (playing || done) return;
    setDone(true);
    setNode("generate");
    report("generate");
  };

  const reset = () => {
    setIteration(1);
    setBoundReached(false);
    setDone(false);
    playSequence(() => {});
  };

  const showButtons = started && !playing && !done && node === "assess";

  return (
    <div ref={hostRef} className="flex flex-col gap-5">
      <div className="flex items-center gap-4">
        <div
          className="h-14 w-14 shrink-0 transition-transform duration-500 ease-out"
          style={{ transform: `rotate(${HEADING_DEG[node]}deg)` }}
        >
          <Image src="/scene/compass_instrument.png" alt="" width={56} height={56} />
        </div>
        <div>
          <p className="font-mono text-xs uppercase tracking-cartouche text-brass">
            {node === "generate" ? "generate" : node}
          </p>
          <p className="font-mono text-[0.65rem] text-graphite">
            iteration {Math.min(iteration, AGENT_MAX_ITERATIONS)} of {AGENT_MAX_ITERATIONS}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-2">
        {AGENT_NODES.map((n, i) => {
          const active = SEQUENCE[i] === node || (node === "generate" && n.id === "generate");
          return (
            <div
              key={n.id}
              className={`rounded-sm border px-2 py-2 text-center font-mono text-[0.6rem] uppercase tracking-cartouche transition-colors duration-300 ${
                active ? "border-brass/60 bg-deep-chart/60 text-brass" : "border-graphite/20 text-graphite"
              }`}
            >
              {n.label}
            </div>
          );
        })}
      </div>

      {showButtons && (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={handleSufficient}
            className="rounded-sm border border-verdigris/60 px-4 py-2 font-mono text-xs uppercase tracking-cartouche text-verdigris transition-colors hover:bg-verdigris/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-verdigris"
          >
            Sufficient
          </button>
          <button
            type="button"
            onClick={handleInsufficient}
            className="rounded-sm border border-brass/60 px-4 py-2 font-mono text-xs uppercase tracking-cartouche text-brass transition-colors hover:bg-brass/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass"
          >
            Insufficient
          </button>
          <span className="text-xs text-graphite">You&rsquo;re the assess step — decide.</span>
        </div>
      )}

      {done && (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-sm text-parchment/80">
            {boundReached
              ? `Bound reached at ${AGENT_MAX_ITERATIONS} iterations — answers with what it has.`
              : "Sufficient — generating the grounded answer."}
          </p>
          <button
            type="button"
            onClick={reset}
            className="font-mono text-xs uppercase tracking-cartouche text-graphite underline decoration-graphite/50 underline-offset-2 transition-colors hover:text-parchment"
          >
            Replay
          </button>
        </div>
      )}
    </div>
  );
}
