"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export interface RailItem {
  id: string;
  label: string;
}

/**
 * A quiet left-edge index for the long-form page — desktop only. Tracks
 * which section is in view via IntersectionObserver (one already-cheap
 * observer per section, same technique as <Reveal/>) and highlights it, so a
 * reader always has a sense of where they are and can jump anywhere. This is
 * the kind of orientation cue a long page earns its keep with; it doesn't
 * need a 3D scene to feel considered.
 */
export function SectionRail({ items }: { items: RailItem[] }) {
  const [activeId, setActiveId] = useState(items[0]?.id ?? "");
  const ratios = useRef<Record<string, number>>({});

  useEffect(() => {
    const els = items
      .map((item) => ({ id: item.id, el: document.getElementById(item.id) }))
      .filter((x): x is { id: string; el: HTMLElement } => x.el !== null);

    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = entry.target.getAttribute("data-rail-id");
          if (id) ratios.current[id] = entry.intersectionRatio;
        }
        let best = activeId;
        let bestRatio = 0;
        for (const [id, ratio] of Object.entries(ratios.current)) {
          if (ratio > bestRatio) {
            bestRatio = ratio;
            best = id;
          }
        }
        if (bestRatio > 0) setActiveId(best);
      },
      { threshold: [0, 0.25, 0.5, 0.75, 1] },
    );

    els.forEach(({ id, el }) => {
      el.setAttribute("data-rail-id", id);
      io.observe(el);
    });
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);

  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const rail = (
    <nav
      aria-label="Sections"
      className="fixed left-6 top-1/2 z-20 hidden -translate-y-1/2 flex-col items-start gap-3 xl:flex"
    >
      {items.map((item) => {
        const active = item.id === activeId;
        return (
          <a
            key={item.id}
            href={`#${item.id}`}
            className="group flex items-center gap-3"
            aria-current={active ? "true" : undefined}
          >
            <span
              className={`h-1.5 w-1.5 shrink-0 rounded-full transition-all duration-300 ${
                active ? "scale-125 bg-brass" : "bg-graphite/40 group-hover:bg-graphite/70"
              }`}
              aria-hidden
            />
            <span
              className={`whitespace-nowrap font-mono text-[0.65rem] uppercase tracking-cartouche opacity-0 transition-opacity duration-200 group-hover:opacity-100 ${
                active ? "text-brass opacity-100" : "text-graphite"
              }`}
            >
              {item.label}
            </span>
          </a>
        );
      })}
    </nav>
  );

  // Portaled straight to <body>: the site-wide page-transition wrapper
  // (app/template.tsx's `.page-enter`) leaves a `transform` on an ancestor
  // after its animation finishes, which makes any `position: fixed`
  // descendant compute relative to *that* element instead of the viewport —
  // a standard CSS gotcha. Escaping via a portal sidesteps it rather than
  // fighting it with more positioning math.
  if (!mounted) return null;
  return createPortal(rail, document.body);
}
