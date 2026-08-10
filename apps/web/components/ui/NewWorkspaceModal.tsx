"use client";

import { useId, useState, type FormEvent } from "react";

import { ApiError } from "@/lib/api";

import { Button } from "./Button";
import { Field } from "./Field";
import { Modal } from "./Modal";

export interface NewWorkspaceModalProps {
  open: boolean;
  onClose: () => void;
  onCreate: (name: string) => Promise<void>;
}

/** A small brass surveyor's-tick mark — the same "plot a new point" idea the
 *  rest of the app's expedition motif uses, just small enough for a dialog
 *  header instead of a full illustration. */
function TickMark() {
  return (
    <svg viewBox="0 0 32 32" className="h-8 w-8 shrink-0" aria-hidden>
      <circle cx="16" cy="16" r="14.5" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.35" />
      <path d="M16 6v6M16 20v6M6 16h6M20 16h6" stroke="currentColor" strokeWidth="1.4" opacity="0.75" />
      <circle cx="16" cy="16" r="3" fill="currentColor" />
    </svg>
  );
}

/**
 * Replaces the native `window.prompt("Name your new workspace")` — same
 * information, an actual design. Reuses Field/Button so it matches every
 * other form in the app rather than introducing a one-off style.
 */
export function NewWorkspaceModal({ open, onClose, onCreate }: NewWorkspaceModalProps) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const titleId = useId();

  function handleClose() {
    if (pending) return;
    setName("");
    setError(null);
    onClose();
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim() || pending) return;
    setPending(true);
    setError(null);
    try {
      await onCreate(name.trim());
      setName("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create the workspace. Try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Modal open={open} onClose={handleClose} labelledBy={titleId}>
      <form
        onSubmit={onSubmit}
        className="neatline relative overflow-hidden bg-linen p-6 sm:p-7"
      >
        {/* A quiet brass rule across the top — the one accent, not a border
            around everything. */}
        <div className="absolute inset-x-0 top-0 h-[2px] bg-gradient-to-r from-transparent via-pewter to-transparent" />

        <div className="flex items-start gap-3">
          <span className="text-pewter">
            <TickMark />
          </span>
          <div>
            <p className="marginalia text-[0.65rem] uppercase tracking-cartouche text-graphite">
              Chart new territory
            </p>
            <h2 id={titleId} className="font-display text-2xl font-medium leading-tight text-ink">
              Name your workspace
            </h2>
          </div>
        </div>

        <div className="mt-6">
          <Field
            label="Workspace name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Acme Research"
            error={error ?? undefined}
            autoFocus
            disabled={pending}
          />
        </div>

        <div className="mt-7 flex items-center justify-end gap-3">
          <Button type="button" variant="ghost" onClick={handleClose} disabled={pending}>
            Cancel
          </Button>
          <Button type="submit" disabled={pending || !name.trim()}>
            {pending ? "Creating…" : "Create workspace"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
