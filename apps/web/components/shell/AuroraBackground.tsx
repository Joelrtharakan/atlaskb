"use client";

// The far parallax layer: a slow verdigris aurora haze drifting behind the whole
// sheet. Built in-house with heavily-blurred CSS gradient blobs (not a second
// WebGL context) so it stays cheap and always-on under the page's real 3D scene.
// Drift freezes under prefers-reduced-motion (handled by the keyframes' media query).
import { useMemo } from "react";

// Import the token map directly (not the barrel) so this always-on background
// never pulls the three.js-dependent atlas-world modules into every page.
import { ATLAS } from "@/components/atlas-world/tokens";

const BLOBS = [
  { top: "-10%", left: "8%", size: 620, hue: ATLAS.verdigris, dur: 34, delay: 0, drift: "aurora-a" },
  { top: "30%", left: "58%", size: 540, hue: ATLAS.brass, dur: 46, delay: -8, drift: "aurora-b" },
  { top: "55%", left: "18%", size: 480, hue: ATLAS.verdigris, dur: 40, delay: -18, drift: "aurora-a" },
];

export function AuroraBackground() {
  const blobs = useMemo(() => BLOBS, []);
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 overflow-hidden"
      style={{ zIndex: 0 }}
    >
      {blobs.map((b, i) => (
        <div
          key={i}
          className="aurora-blob"
          style={{
            position: "absolute",
            top: b.top,
            left: b.left,
            width: b.size,
            height: b.size,
            borderRadius: "50%",
            background: `radial-gradient(circle at 50% 50%, ${b.hue} 0%, transparent 68%)`,
            opacity: b.hue === ATLAS.brass ? 0.05 : 0.08,
            filter: "blur(90px)",
            animation: `${b.drift} ${b.dur}s ease-in-out ${b.delay}s infinite`,
            willChange: "transform",
          }}
        />
      ))}
    </div>
  );
}
