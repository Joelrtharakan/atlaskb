"use client";

import { useMemo } from "react";
import dynamic from "next/dynamic";

import { buildAtlas } from "@/components/living-atlas/atlas-data";
import { PLACEHOLDER_DOCUMENTS } from "@/components/living-atlas/documents";
import { useRetrieval } from "./retrieval";

const LivingAtlas = dynamic(() => import("@/components/living-atlas/LivingAtlas"), { ssr: false });

/**
 * The docked, retrieval-reactive Living Atlas for the chat page. Node index N
 * maps to document N, so a lit beacon corresponds to a cited source.
 */
export default function ChatAtlas() {
  const { atlas } = useRetrieval();
  // One node per document so citations line up with nodes.
  const data = useMemo(() => buildAtlas(PLACEHOLDER_DOCUMENTS.length), []);

  return (
    <div className="absolute inset-0" aria-hidden="true">
      <LivingAtlas mode="reactive" data={data} state={atlas} />
    </div>
  );
}
