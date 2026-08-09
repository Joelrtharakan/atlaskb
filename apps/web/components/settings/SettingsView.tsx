"use client";

import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { motionDisabled, setMotionDisabled, subscribeMotion } from "@/lib/motion";
import type { LLMHealth } from "@/lib/types";

// Instrument-panel controls: brass lever + dial affordances in CSS/SVG (no 3D
// scene — a settings page is low-drama). Lever/knob styling referenced from
// Aceternity/Magic UI toggles, rebuilt in the brass/verdigris palette.

/** A brass lever toggle (an accessible switch). */
function Lever({
  on,
  onChange,
  label,
  hint,
}: {
  on: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint: string;
}) {
  return (
    <div className="flex items-center justify-between gap-6 border-b border-graphite/15 py-4">
      <div>
        <p className="text-sm text-ink">{label}</p>
        <p className="mt-0.5 text-xs text-graphite">{hint}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-label={label}
        onClick={() => onChange(!on)}
        className="relative h-7 w-14 shrink-0 rounded-full border transition-colors"
        style={{
          backgroundColor: on ? "#3F6259" : "#D9DCD1",
          borderColor: "#B08D4F",
        }}
      >
        <span
          className="absolute top-0.5 h-5 w-5 rounded-full shadow-sm transition-all"
          style={{
            left: on ? "1.9rem" : "0.15rem",
            background: "linear-gradient(160deg,#C9A868,#8A6B33)", // brass knob
          }}
        />
      </button>
    </div>
  );
}

/** A brass-framed status dial (read-only readout). */
function Dial({ health }: { health: LLMHealth | null }) {
  const ok = !!health?.reachable && !!health?.model_available;
  return (
    <div className="flex items-center gap-4 border border-graphite/25 bg-ink/[0.03] p-4">
      <svg width="56" height="56" viewBox="0 0 56 56" aria-hidden className="shrink-0">
        <circle cx="28" cy="28" r="26" fill="#12181F" stroke="#B08D4F" strokeWidth="2" />
        {/* ticks */}
        {Array.from({ length: 12 }).map((_, i) => {
          const a = (i / 12) * Math.PI * 2;
          return (
            <line
              key={i}
              x1={28 + Math.cos(a) * 21}
              y1={28 + Math.sin(a) * 21}
              x2={28 + Math.cos(a) * 24}
              y2={28 + Math.sin(a) * 24}
              stroke="#B08D4F"
              strokeWidth="1"
              opacity={0.7}
            />
          );
        })}
        {/* needle: right (ok) vs left (down) */}
        <line
          x1="28"
          y1="28"
          x2={ok ? 44 : 14}
          y2={ok ? 18 : 18}
          stroke={ok ? "#3F6259" : "#B08D4F"}
          strokeWidth="2.5"
        />
        <circle cx="28" cy="28" r="3" fill="#B08D4F" />
      </svg>
      <div>
        <p className="font-mono text-xs uppercase tracking-cartouche text-graphite">
          Model routing
        </p>
        <p className="mt-0.5 text-sm text-ink">
          {health ? `${health.provider} · ${health.model}` : "reading…"}
        </p>
        <p className="mt-0.5 text-xs" style={{ color: ok ? "#3F6259" : "#B08D4F" }}>
          {health ? (ok ? "reachable" : "unavailable") : ""}
        </p>
      </div>
    </div>
  );
}

export function SettingsView() {
  const [health, setHealth] = useState<LLMHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [motionOff, setMotionOff] = useState(false);

  useEffect(() => {
    setMotionOff(motionDisabled());
    const unsub = subscribeMotion(() => setMotionOff(motionDisabled()));
    api
      .llmHealth()
      .then(setHealth)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Couldn't read the model status."),
      );
    return unsub;
  }, []);

  return (
    <section className="mx-auto flex min-h-full max-w-2xl flex-col gap-6 p-4 sm:p-8">
      <div>
        <p className="font-mono text-xs uppercase tracking-cartouche text-graphite">
          Instrument panel
        </p>
        <h1 className="font-display text-3xl font-medium text-ink">Settings</h1>
      </div>

      {error ? (
        <p role="alert" className="border border-ink bg-ink/5 px-3 py-2 text-sm text-ink">
          {error}
        </p>
      ) : null}

      <Dial health={health} />

      <div>
        <Lever
          on={!motionOff}
          onChange={(v) => setMotionDisabled(!v)}
          label="Atlas motion"
          hint="Animate the 3D instruments. Off freezes every atlas to a static frame."
        />
      </div>

      <p className="text-xs text-graphite">
        The model provider is configured on the server (env). API-key management is available via
        the API today; a panel here is planned.
      </p>
    </section>
  );
}
