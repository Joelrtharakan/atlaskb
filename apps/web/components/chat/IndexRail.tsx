"use client";

import {
  PLACEHOLDER_DOCUMENTS,
  TERRITORY_LABELS,
  type Territory,
} from "@/components/living-atlas/documents";
import { useRetrieval } from "./retrieval";

/**
 * Index Rail — the map's legend. Deliberately quiet (see the design plan's §6):
 * no motion, no beacon/meridian. It reflects which documents are currently lit,
 * but only through neutral ink emphasis — the amber lives on the atlas and in
 * the transcript citations, never here.
 */
export default function IndexRail() {
  const { atlas } = useRetrieval();
  const activeIds = new Set(atlas.activeNodes.map((i) => PLACEHOLDER_DOCUMENTS[i]?.id));

  const territories = Object.keys(TERRITORY_LABELS) as Territory[];

  return (
    <nav className="flex h-full flex-col gap-6 overflow-y-auto p-5">
      <div>
        <p className="marginalia text-[0.65rem] uppercase tracking-cartouche text-pewter">Tenant</p>
        <p className="mt-1 font-mono text-sm text-ink">acme-corp</p>
      </div>

      {territories.map((territory) => (
        <div key={territory}>
          <p className="marginalia mb-2 text-[0.65rem] uppercase tracking-cartouche text-pewter">
            {TERRITORY_LABELS[territory]}
          </p>
          <ul className="space-y-1 border-l border-graphite/25 pl-3">
            {PLACEHOLDER_DOCUMENTS.filter((d) => d.territory === territory).map((doc) => {
              const active = activeIds.has(doc.id);
              return (
                <li
                  key={doc.id}
                  className="flex items-center gap-2 text-sm text-graphite"
                  aria-current={active ? "true" : undefined}
                >
                  {/* Neutral static marker — no beacon on this quiet surface. */}
                  <span className="text-graphite/40" aria-hidden>
                    {active ? "▸" : "·"}
                  </span>
                  <span className={active ? "font-medium text-ink" : undefined}>{doc.title}</span>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
