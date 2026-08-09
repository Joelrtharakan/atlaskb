"use client";

import { useMemo } from "react";

// In-house "Threads": a field of thin brass survey lines suggesting triangulation
// lines being plotted. Rebuilt from scratch (React Bits/npm unavailable) as a
// lightweight SVG — no per-frame JS. Intensity rises while the operator is typing
// ("plotting"), eased via CSS opacity transition. Drift freezes on reduced motion.

// Small deterministic PRNG so the line field is stable between renders.
function seeded(n: number) {
  let s = n;
  return () => {
    s = (s * 1103515245 + 12345) & 0x7fffffff;
    return s / 0x7fffffff;
  };
}

export function ThreadsBackground({ active }: { active: boolean }) {
  const lines = useMemo(() => {
    const rnd = seeded(20260809);
    return Array.from({ length: 34 }, () => {
      // Anchor near a few plotting stations, fan out to spread endpoints.
      const ax = rnd() * 100;
      const ay = rnd() * 100;
      const angle = rnd() * Math.PI * 2;
      const len = 30 + rnd() * 90;
      return {
        x1: ax,
        y1: ay,
        x2: ax + Math.cos(angle) * len,
        y2: ay + Math.sin(angle) * len,
        w: 0.1 + rnd() * 0.18,
      };
    });
  }, []);

  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <svg
        className="threads-drift h-full w-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        style={{
          opacity: active ? 0.22 : 0.08,
          transition: "opacity 0.5s ease",
        }}
      >
        {lines.map((l, i) => (
          <line
            key={i}
            x1={l.x1}
            y1={l.y1}
            x2={l.x2}
            y2={l.y2}
            stroke="#C08A45"
            strokeWidth={l.w}
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>
    </div>
  );
}
