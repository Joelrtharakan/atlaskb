import { Fragment, type ReactNode } from "react";

import { CitationMarker } from "@/components/ui/CitationMarker";
import type { ChatResponse, ScoredChunk } from "@/lib/types";

export type NumberedSource = {
  index: number;
  chunkId: string;
  chunk: ScoredChunk | undefined;
};

/** Assign [1], [2], … to each unique cited chunk in first-appearance order. */
export function numberSources(resp: ChatResponse): {
  order: NumberedSource[];
  indexOf: Map<string, number>;
} {
  const indexOf = new Map<string, number>();
  const order: NumberedSource[] = [];
  const byId = new Map(resp.retrieved.map((c) => [c.chunk_id, c] as const));

  for (const cit of resp.citations) {
    for (const id of cit.chunk_ids) {
      if (!indexOf.has(id)) {
        const index = order.length + 1;
        indexOf.set(id, index);
        order.push({ index, chunkId: id, chunk: byId.get(id) });
      }
    }
  }
  return { order, indexOf };
}

/**
 * Render the answer prose with inline citation markers. Each claim's markers are
 * inserted right after the first place that claim's text appears in the answer
 * (the backend's claims are usually verbatim spans). Any markers we can't place
 * inline are appended at the end so no citation is ever dropped.
 */
export interface CitationRenderOptions {
  /** Notified with a document id on citation hover/focus, null on leave. */
  onHoverDoc?: (documentId: string | null) => void;
}

export function renderAnswerWithCitations(
  resp: ChatResponse,
  opts: CitationRenderOptions = {},
): ReactNode {
  const { order, indexOf } = numberSources(resp);
  const answer = resp.answer;
  const lower = answer.toLowerCase();

  const hoverHandler = (chunk: ScoredChunk | undefined) =>
    opts.onHoverDoc && chunk
      ? (hovering: boolean) => opts.onHoverDoc?.(hovering ? chunk.document_id : null)
      : undefined;

  type Insertion = { pos: number; indices: number[] };
  const insertions: Insertion[] = [];
  const placed = new Set<number>();

  for (const cit of resp.citations) {
    const indices = cit.chunk_ids
      .map((id) => indexOf.get(id))
      .filter((n): n is number => n != null);
    if (indices.length === 0) continue;

    const claim = cit.claim?.trim().toLowerCase();
    const at = claim ? lower.indexOf(claim) : -1;
    if (claim && at >= 0) {
      insertions.push({ pos: at + claim.length, indices });
      indices.forEach((i) => placed.add(i));
    }
  }

  // Markers we couldn't anchor inline get appended after the prose.
  const trailing = order.map((s) => s.index).filter((i) => !placed.has(i));

  insertions.sort((a, b) => a.pos - b.pos);

  const nodes: ReactNode[] = [];
  let cursor = 0;
  insertions.forEach((ins, k) => {
    const pos = Math.max(ins.pos, cursor);
    nodes.push(<Fragment key={`t-${k}`}>{answer.slice(cursor, pos)}</Fragment>);
    ins.indices.forEach((i) => {
      const src = order.find((s) => s.index === i);
      nodes.push(
        <CitationMarker
          key={`c-${k}-${i}`}
          index={i}
          chunk={src?.chunk}
          onHoverChange={hoverHandler(src?.chunk)}
        />,
      );
    });
    cursor = pos;
  });
  nodes.push(<Fragment key="tail">{answer.slice(cursor)}</Fragment>);

  if (trailing.length > 0) {
    nodes.push(
      <Fragment key="trailing">
        {" "}
        {trailing.map((i) => {
          const src = order.find((s) => s.index === i);
          return (
            <CitationMarker
              key={`tr-${i}`}
              index={i}
              chunk={src?.chunk}
              onHoverChange={hoverHandler(src?.chunk)}
            />
          );
        })}
      </Fragment>,
    );
  }

  return nodes;
}
