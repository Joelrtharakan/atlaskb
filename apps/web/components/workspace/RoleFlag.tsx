"use client";

import { useEffect, useState } from "react";

import type { Role } from "@/lib/types";

// Expedition flag per member; color reads the role. SVG, not a 3D scene (per the
// restraint rule). Hover/reveal timing referenced from Aceternity/Magic UI micro-
// interactions, rebuilt in the token palette. Respects prefers-reduced-motion.
const ROLE_COLOR: Record<Role, string> = {
  admin: "#B08D4F", // brass
  editor: "#3F6259", // verdigris
  viewer: "#8793A0", // pewter
};

export function RoleFlag({ role, plant = false }: { role: Role; plant?: boolean }) {
  const [raised, setRaised] = useState(!plant);
  useEffect(() => {
    if (!plant) return;
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setRaised(true);
      return;
    }
    const t = setTimeout(() => setRaised(true), 30);
    return () => clearTimeout(t);
  }, [plant]);

  return (
    <svg
      width="14"
      height="18"
      viewBox="0 0 14 18"
      aria-hidden
      className="inline-block shrink-0"
      style={{
        transform: raised ? "translateY(0) scale(1)" : "translateY(4px) scale(0.5)",
        opacity: raised ? 1 : 0,
        transformOrigin: "2px 17px", // pivot at the flagpole base
        transition: "transform 500ms cubic-bezier(.16,1,.3,1), opacity 400ms ease",
      }}
    >
      {/* pole */}
      <line x1="2" y1="1" x2="2" y2="17" stroke="#515C63" strokeWidth="1.2" />
      {/* pennant */}
      <path d="M2 2 L12 4.5 L2 7 Z" fill={ROLE_COLOR[role]} />
    </svg>
  );
}
