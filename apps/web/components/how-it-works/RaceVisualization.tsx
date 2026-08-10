"use client";

import { useEffect, useRef, useState } from "react";

import { useReducedMotion } from "@/components/living-atlas/use-capabilities";
import { LATENCY_ROWS } from "@/lib/how-it-works-content";

// Real p50s — mirrors eval/results/load-latest.json's chat_cold / chat_warm
// phases (23180.9ms / 20.0ms). Keep these in sync with that file if it's
// re-run; the on-screen durations below are *derived* from these two
// numbers, not picked by feel.
const COLD_MS = LATENCY_ROWS.find((r) => r.id === "chat-cold")!.p50; // "23.2 s"
const WARM_MS = LATENCY_ROWS.find((r) => r.id === "chat-warm")!.p50; // "20 ms"
const COLD_REAL_MS = 23200;
const WARM_REAL_MS = 20;

// Log-scale compression: the real ~1160x gap between 20ms and 23,200ms would
// either be an unwatchable 23-second animation at true scale, or a fake
// "instant vs a bit slower" gesture at arbitrary scale. Mapping both onto a
// shared log axis and reading the on-screen duration off that axis keeps the
// *relative* gap honest — cached finishes near-instantly, cold is still
// visibly crawling — while the whole thing resolves in a few seconds.
const SCREEN_MIN_MS = 220; // warm: reads as "almost instant", not literally 0
const SCREEN_MAX_MS = 4600; // cold: the full budget for this section's reveal

function compressedDuration(realMs: number): number {
  const lo = Math.log10(WARM_REAL_MS);
  const hi = Math.log10(COLD_REAL_MS);
  const t = (Math.log10(realMs) - lo) / (hi - lo);
  return SCREEN_MIN_MS + t * (SCREEN_MAX_MS - SCREEN_MIN_MS);
}

const COLD_DURATION_MS = compressedDuration(COLD_REAL_MS);
const WARM_DURATION_MS = compressedDuration(WARM_REAL_MS);

function Track({
  label,
  progress,
  done,
  realLabel,
  accent,
}: {
  label: string;
  progress: number;
  done: boolean;
  realLabel: string;
  accent: "brass" | "verdigris";
}) {
  const barColor = accent === "brass" ? "bg-brass" : "bg-verdigris";
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <p className="font-mono text-[0.65rem] uppercase tracking-cartouche text-graphite">{label}</p>
        <p className={`font-mono text-sm tabular-nums ${done ? "text-parchment" : "text-graphite"}`}>
          {done ? realLabel : " "}
        </p>
      </div>
      <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-deep-chart">
        <div
          className={`h-full rounded-full ${barColor}`}
          style={{ width: `${progress * 100}%` }}
        />
      </div>
    </div>
  );
}

/**
 * Section 5's centerpiece: two request paths racing at a speed ratio derived
 * from the real measured p50s, not an arbitrary "cache is faster" gesture.
 * Starts on scroll-into-view; reduced-motion shows both finished immediately.
 */
export function RaceVisualization() {
  const reducedMotion = useReducedMotion();
  const hostRef = useRef<HTMLDivElement>(null);
  const [started, setStarted] = useState(false);
  const [coldProgress, setColdProgress] = useState(0);
  const [warmProgress, setWarmProgress] = useState(0);
  const [coldDone, setColdDone] = useState(false);
  const [warmDone, setWarmDone] = useState(false);

  // See DemoLivingAtlas's comment on the same pattern: useReducedMotion()
  // resolves asynchronously, so this has to be synced in an effect rather
  // than read once via a lazy useState initializer.
  useEffect(() => {
    if (!reducedMotion) return;
    setColdProgress(1);
    setWarmProgress(1);
    setColdDone(true);
    setWarmDone(true);
  }, [reducedMotion]);

  useEffect(() => {
    if (reducedMotion || started) return;
    const el = hostRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setStarted(true);
          io.disconnect();
        }
      },
      { threshold: 0.4 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [reducedMotion, started]);

  useEffect(() => {
    if (!started || reducedMotion) return;
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const elapsed = now - start;
      const cp = Math.min(1, elapsed / COLD_DURATION_MS);
      const wp = Math.min(1, elapsed / WARM_DURATION_MS);
      setColdProgress(cp);
      setWarmProgress(wp);
      if (wp >= 1) setWarmDone(true);
      if (cp >= 1) setColdDone(true);
      if (cp < 1 || wp < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [started, reducedMotion]);

  return (
    <div ref={hostRef} className="flex flex-col gap-5">
      <Track label="Cached request" progress={warmProgress} done={warmDone} realLabel={WARM_MS} accent="verdigris" />
      <Track label="Cold request" progress={coldProgress} done={coldDone} realLabel={COLD_MS} accent="brass" />
      <p className="text-xs text-graphite">
        Same speed ratio as the real measurement — cached finishes in roughly{" "}
        <span className="text-parchment/70">1/1000th</span> the time, compressed onto a shared log
        scale so both stay watchable.
      </p>
    </div>
  );
}
