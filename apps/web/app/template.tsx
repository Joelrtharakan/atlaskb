"use client";

import type { ReactNode } from "react";

/**
 * Next re-mounts a template on every navigation, so this gives one cohesive
 * page-transition: incoming content fades + rises as a single move (see
 * `.page-enter` in globals.css). Rebuilt in-house — GSAP is unavailable here —
 * and disabled under prefers-reduced-motion.
 */
export default function Template({ children }: { children: ReactNode }) {
  return <div className="page-enter">{children}</div>;
}
