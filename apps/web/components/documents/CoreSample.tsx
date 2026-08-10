"use client";

import { ATLAS } from "@/components/atlas-world";
import type { ChunkSample } from "@/lib/types";

// Subtle horizontal "grain" — real core-sample photos read as banded rock,
// not flat paint chips; this is the cheapest way to suggest that texture
// without an image asset (see the how-it-works page for why we're done
// depending on illustration assets that may or may not be usable).
const GRAIN_BG = "repeating-linear-gradient(to bottom, rgba(0,0,0,0.14) 0, rgba(0,0,0,0.14) 1px, transparent 1px, transparent 5px)";

/** Interpolate two #rrggbb colors. */
function hexLerp(a: string, b: string, t: number): string {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  const c = pa.map((v, i) => Math.round(v + (pb[i] - v) * Math.max(0, Math.min(1, t))));
  return `#${c.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

/** Color a stratum: low confidence → brass, high confidence → verdigris. */
export function colorForChunk(c: ChunkSample): string {
  return hexLerp(ATLAS.brass, ATLAS.verdigris, c.confidence);
}

const MIN_BAND_PX = 12;
const MAX_BAND_PX = 56;
// A band tall enough to fit its index number without crowding.
const LABEL_MIN_PX = 20;

/**
 * The document's chunks as a geological core sample — a vertical
 * stratigraphy column instead of a 3D cylinder. The cylinder looked the
 * part but couldn't actually scale: dozens of chunks became dozens of
 * sub-pixel slivers with no way to tell them apart. Every stratum here gets
 * a real, clickable minimum height and the column scrolls instead of
 * cramming everything into a fixed box, so nothing chunk gets lost —
 * legibility was the whole point of "core sample," so this fixes that
 * directly rather than re-skinning the same problem.
 *
 * Band height is relative to the longest chunk in *this* document (not a
 * fixed scale), so short documents and long ones both read with good
 * contrast between their own chunks. Color keeps the existing meaning: low
 * embedding-centrality (outlier/boilerplate) → brass, high (representative)
 * → verdigris.
 */
export function CoreSample({
  layers,
  hoveredId,
  onHover,
}: {
  layers: ChunkSample[];
  hoveredId: string | null;
  onHover: (id: string | null) => void;
}) {
  const maxLen = Math.max(...layers.map((l) => l.length), 1);

  return (
    <div className="flex h-full w-full">
      {/* Depth ruler — chunk index, only where a band has room for it. */}
      <div className="flex w-8 shrink-0 flex-col gap-px overflow-y-auto py-px [scrollbar-width:none]" aria-hidden>
        {layers.map((l) => {
          const h = Math.round(MIN_BAND_PX + (MAX_BAND_PX - MIN_BAND_PX) * (l.length / maxLen));
          return (
            <div key={l.chunk_id} style={{ height: h }} className="flex items-center justify-end pr-1.5">
              {h >= LABEL_MIN_PX ? (
                <span className="font-mono text-[9px] leading-none text-graphite/70">{l.chunk_index}</span>
              ) : null}
            </div>
          );
        })}
      </div>

      {/* The core itself. */}
      <div className="min-w-0 flex-1 overflow-y-auto border-l border-graphite/20 pl-2">
        <ul className="flex flex-col gap-px">
          {layers.map((l) => {
            const h = Math.round(MIN_BAND_PX + (MAX_BAND_PX - MIN_BAND_PX) * (l.length / maxLen));
            const active = hoveredId === l.chunk_id;
            return (
              <li key={l.chunk_id}>
                <button
                  type="button"
                  style={{ height: h, backgroundColor: colorForChunk(l), backgroundImage: GRAIN_BG }}
                  onMouseEnter={() => onHover(l.chunk_id)}
                  onMouseLeave={() => onHover(null)}
                  onFocus={() => onHover(l.chunk_id)}
                  onBlur={() => onHover(null)}
                  onClick={() => onHover(active ? null : l.chunk_id)}
                  aria-pressed={active}
                  aria-label={`Chunk ${l.chunk_index}${l.page_num != null ? `, page ${l.page_num}` : ""}`}
                  className={`block w-full rounded-[2px] transition-[transform,box-shadow] duration-150 focus-visible:outline-none ${
                    active
                      ? "translate-x-1 shadow-[-3px_0_0_0_theme(colors.beacon)]"
                      : "hover:translate-x-0.5"
                  }`}
                />
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
