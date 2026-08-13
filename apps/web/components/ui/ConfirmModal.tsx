"use client";

import { useId, useState } from "react";

import { Button } from "./Button";
import { Modal } from "./Modal";

/** A small brass-toned warning tick — same expedition-instrument motif as
 *  NewWorkspaceModal's compass mark, but the caution reading of it: an
 *  interrupted line instead of a steady one. */
function CautionMark() {
  return (
    <svg viewBox="0 0 32 32" className="h-8 w-8 shrink-0" aria-hidden>
      <circle cx="16" cy="16" r="14.5" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.35" />
      <path d="M16 9v10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="16" cy="23" r="1.4" fill="currentColor" />
    </svg>
  );
}

export interface ConfirmModalProps {
  open: boolean;
  onClose: () => void;
  /** May reject — the modal stays open and surfaces the error rather than
   * closing on a failed destructive action. */
  onConfirm: () => Promise<void> | void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Reserved for genuinely destructive/irreversible actions — renders the
   * confirm button in the danger variant. Defaults on, since this component
   * exists specifically to replace `window.confirm`'s "this can't be
   * undone" pattern; pass `false` for a merely-disruptive-but-safe confirm. */
  destructive?: boolean;
}

/**
 * Replaces `window.confirm` wherever the app needs to confirm a destructive
 * action — same shell/motion Modal already gives NewWorkspaceModal, so a
 * "delete this" prompt reads as part of the same product instead of
 * browser chrome. Async-aware: while `onConfirm` is pending, both buttons
 * disable and the confirm label shows in-progress state; a thrown error
 * surfaces inline instead of silently closing.
 */
export function ConfirmModal({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = "Delete",
  cancelLabel = "Cancel",
  destructive = true,
}: ConfirmModalProps) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();

  function handleClose() {
    if (pending) return;
    setError(null);
    onClose();
  }

  async function handleConfirm() {
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      await onConfirm();
    } catch {
      setError("That didn't go through. Try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Modal open={open} onClose={handleClose} labelledBy={titleId}>
      <div className="neatline relative overflow-hidden bg-linen p-6 sm:p-7">
        <div
          className={`absolute inset-x-0 top-0 h-[2px] bg-gradient-to-r from-transparent to-transparent ${
            destructive ? "via-signal-red" : "via-pewter"
          }`}
        />

        <div className="flex items-start gap-3">
          <span className={destructive ? "text-signal-red" : "text-pewter"}>
            <CautionMark />
          </span>
          <div>
            <p className="marginalia text-[0.65rem] uppercase tracking-cartouche text-graphite">
              {destructive ? "This can't be undone" : "Confirm"}
            </p>
            <h2 id={titleId} className="font-display text-2xl font-medium leading-tight text-ink">
              {title}
            </h2>
          </div>
        </div>

        <p className="mt-4 text-sm leading-relaxed text-graphite">{description}</p>

        {error ? (
          <p role="alert" className="mt-4 border border-signal-red/60 bg-signal-red/10 px-3 py-2 text-sm text-ink">
            {error}
          </p>
        ) : null}

        <div className="mt-7 flex items-center justify-end gap-3">
          <Button type="button" variant="ghost" onClick={handleClose} disabled={pending}>
            {cancelLabel}
          </Button>
          <Button
            type="button"
            variant={destructive ? "danger" : "solid"}
            onClick={handleConfirm}
            disabled={pending}
          >
            {pending ? "Working…" : confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
