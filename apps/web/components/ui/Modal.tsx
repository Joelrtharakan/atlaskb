"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  /** Accessible name for the dialog — required, not decorative. */
  labelledBy: string;
  children: ReactNode;
}

/**
 * A small, accessible dialog shell — replaces native `window.prompt`/
 * `window.confirm` wherever the app needs to ask for something richer than
 * a browser-chrome box lets it style. Escape and backdrop-click both close;
 * portaled straight to `document.body` so it always sits above everything
 * regardless of where it's mounted (the same fixed-position containing-block
 * issue the how-it-works section rail hit applies here too).
 */
export function Modal({ open, onClose, labelledBy, children }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    // Move focus into the panel so Tab/Escape work immediately.
    const first = panelRef.current?.querySelector<HTMLElement>(
      "input, button, select, textarea, [tabindex]",
    );
    first?.focus();
    // Trap background scroll while open.
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="modal-backdrop-in absolute inset-0 bg-chart-navy/80 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        className="modal-panel-in relative w-full max-w-sm"
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
