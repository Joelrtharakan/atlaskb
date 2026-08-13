"use client";

import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import type { ConversationSummary } from "@/lib/types";

import { ConfirmModal } from "../ui/ConfirmModal";

/** Recent-conversations switcher for the current workspace. A dropdown panel
 * rather than a permanent sidebar — the chat transcript is the primary
 * surface, so this stays out of the way until asked for (Escape or clicking
 * outside its trigger closes it, same as any other menu in this app). */
export function ConversationList({
  activeId,
  onNavigate,
  onDeletedActive,
  onClose,
}: {
  activeId: string;
  onNavigate: (id: string) => void;
  onDeletedActive: () => void;
  onClose: () => void;
}) {
  const [conversations, setConversations] = useState<ConversationSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The conversation a delete has been requested for, awaiting confirmation
  // in the modal below — not yet an in-flight request (ConfirmModal owns
  // that pending state itself).
  const [confirmTarget, setConfirmTarget] = useState<ConversationSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listConversations()
      .then((cs) => {
        if (!cancelled) setConversations(cs);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Couldn't load conversations.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function requestDelete(e: React.MouseEvent | React.KeyboardEvent, c: ConversationSummary) {
    e.stopPropagation();
    setConfirmTarget(c);
  }

  async function confirmDelete() {
    if (!confirmTarget) return;
    const id = confirmTarget.id;
    await api.deleteConversation(id);
    setConversations((cs) => (cs ?? []).filter((c) => c.id !== id));
    setConfirmTarget(null);
    if (id === activeId) onDeletedActive();
  }

  return (
    <div
      role="dialog"
      aria-label="Recent conversations"
      className="absolute left-0 top-full z-30 mt-1 max-h-[70vh] w-80 overflow-y-auto border border-graphite/30 bg-linen shadow-lg"
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
    >
      {conversations === null ? (
        <p className="p-4 text-xs text-graphite">Loading…</p>
      ) : error ? (
        <p className="p-4 text-xs text-signal-red">{error}</p>
      ) : conversations.length === 0 ? (
        <p className="p-4 text-xs text-graphite">No conversations yet.</p>
      ) : (
        <ul>
          {conversations.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => onNavigate(c.id)}
                className={`flex w-full items-center justify-between gap-2 border-b border-graphite/15 px-3 py-2 text-left transition-colors hover:bg-pewter/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter ${
                  c.id === activeId ? "bg-pewter/10" : ""
                }`}
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-ink">{c.title || "Untitled"}</span>
                  <span className="marginalia block text-[0.65rem] text-graphite">
                    {formatRelative(c.created_at)}
                  </span>
                </span>
                <span
                  role="button"
                  tabIndex={0}
                  aria-label="Delete conversation"
                  onClick={(e) => requestDelete(e, c)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      requestDelete(e, c);
                    }
                  }}
                  className="shrink-0 rounded-sm px-1.5 py-1 text-xs text-graphite transition-colors hover:text-signal-red focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter disabled:opacity-50"
                >
                  ✕
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <ConfirmModal
        open={confirmTarget !== null}
        onClose={() => setConfirmTarget(null)}
        onConfirm={confirmDelete}
        title="Delete this conversation?"
        description={
          confirmTarget
            ? `"${confirmTarget.title || "Untitled"}" and every message in it will be gone for good.`
            : ""
        }
        confirmLabel="Delete"
      />
    </div>
  );
}
