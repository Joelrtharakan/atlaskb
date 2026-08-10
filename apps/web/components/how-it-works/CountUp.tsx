"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Counts up to `to` once, the first time it scrolls into view. Plain
 * IntersectionObserver + requestAnimationFrame — no GSAP dependency needed
 * for a one-shot number tween, and it works identically whether or not the
 * pinned 3D experience around it is running.
 */
export function CountUp({ to, durationMs = 900 }: { to: number; durationMs?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [value, setValue] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        io.disconnect();
        const start = performance.now();
        const tick = (now: number) => {
          const p = Math.min(1, (now - start) / durationMs);
          const eased = 1 - Math.pow(1 - p, 3); // power3.out, matches the rest of the site
          setValue(Math.round(to * eased));
          if (p < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      },
      { threshold: 0.4 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [to, durationMs]);

  return <span ref={ref}>{value.toLocaleString()}</span>;
}
