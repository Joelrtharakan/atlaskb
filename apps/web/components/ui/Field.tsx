import { forwardRef, useId, type InputHTMLAttributes } from "react";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  error?: string;
};

// Labeled text input. Label is always present (never a placeholder-as-label),
// errors are wired via aria-describedby, and focus is a visible pewter ring.
export const Field = forwardRef<HTMLInputElement, Props>(function Field(
  { label, hint, error, id, className = "", ...props },
  ref,
) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={inputId}
        className="font-mono text-xs uppercase tracking-cartouche text-graphite"
      >
        {label}
      </label>
      {hint ? (
        <p id={hintId} className="text-xs text-graphite">
          {hint}
        </p>
      ) : null}
      <input
        ref={ref}
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={
          "w-full rounded-none border border-graphite/50 bg-linen/60 px-3 py-2 " +
          "text-ink placeholder:text-graphite/60 " +
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter " +
          "focus-visible:ring-offset-2 focus-visible:ring-offset-linen " +
          (error ? "border-ink " : "") +
          className
        }
        {...props}
      />
      {error ? (
        <p id={errorId} role="alert" className="text-xs text-ink">
          {error}
        </p>
      ) : null}
    </div>
  );
});
