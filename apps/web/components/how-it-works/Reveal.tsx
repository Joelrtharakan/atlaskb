"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Fades a section in the first time it crosses 20% into the viewport. Plain
 * IntersectionObserver + CSS, not GSAP — this is the static/reduced-motion
 * reading path, which must stay cheap and correct with zero 3D or scroll-jack
 * dependency. The global `prefers-reduced-motion` rule in globals.css already
 * zeroes the transition duration, so no extra branching is needed here.
 */
export function Reveal({ children, className = "" }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          io.disconnect();
        }
      },
      { threshold: 0.2 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div ref={ref} className={`hiw-reveal ${visible ? "hiw-reveal-in" : ""} ${className}`}>
      {children}
    </div>
  );
}
