"use client";

import { useState } from "react";

import { useRetrieval } from "./retrieval";

/**
 * The ruled input — writing on the chart. On submit, its rule carries a
 * travelling beacon underline while retrieval is in progress.
 */
export default function QuestionInput() {
  const { ask, busy } = useRetrieval();
  const [value, setValue] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (busy || !value.trim()) return;
    ask(value);
    setValue("");
  };

  return (
    <form onSubmit={submit} className="relative px-6 py-4">
      <div className="flex items-center gap-3">
        <span aria-hidden className="font-mono text-pewter">
          ›
        </span>
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={busy}
          placeholder="Ask a question…"
          aria-label="Ask a question"
          className="w-full bg-transparent py-1 text-ink placeholder:text-graphite/50 focus:outline-none disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={busy || !value.trim()}
          className="font-mono text-sm uppercase tracking-cartouche text-pewter transition-colors hover:text-ink disabled:opacity-40"
        >
          ↵
        </button>
      </div>

      {/* The rule. A travelling beacon segment runs along it while busy. */}
      <div className="relative mt-1 h-px w-full bg-graphite/30">
        {busy && (
          <span className="absolute left-0 top-0 h-px w-1/3 animate-[survey_1.1s_linear_infinite] bg-beacon" />
        )}
      </div>
    </form>
  );
}
