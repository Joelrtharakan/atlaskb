"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { ContourProgress } from "@/components/ui/ContourProgress";
import { ApiError, api } from "@/lib/api";
import type { DocumentOut } from "@/lib/types";

const ACCEPT = ".pdf,.md,.markdown,.html,.htm,.docx,.xlsx,.pptx,.csv,.txt";

// Upload a source file, then hand the created document back so the register can
// poll it to ready/failed. Errors state what happened and what to do next.
export function UploadControl({ onUploaded }: { onUploaded: (doc: DocumentOut) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleUpload() {
    if (!file) {
      setError("Choose a file first.");
      return;
    }
    setError(null);
    setUploading(true);
    try {
      const doc = await api.uploadDocument(file);
      onUploaded(doc);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "The upload didn't reach the API. Check the backend is running and try again.",
      );
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="border border-graphite/30 bg-linen/50 p-4">
      <p className="font-mono text-xs uppercase tracking-cartouche text-graphite">Add territory</p>
      <p className="mt-1 text-sm text-graphite">
        Upload a PDF, Word, Excel, CSV, plain text, PowerPoint, Markdown, or HTML file. AtlasKB
        surveys it into searchable chunks.
      </p>

      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <label className="flex-1">
          <span className="sr-only">Choose a file to upload</span>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            onChange={(e) => {
              setError(null);
              setFile(e.target.files?.[0] ?? null);
            }}
            className={
              "block w-full text-sm text-ink file:mr-3 file:cursor-pointer file:border " +
              "file:border-pewter file:bg-transparent file:px-3 file:py-1.5 " +
              "file:font-mono file:text-xs file:uppercase file:tracking-cartouche file:text-ink " +
              "hover:file:bg-pewter/15 focus-visible:outline-none focus-visible:ring-2 " +
              "focus-visible:ring-pewter focus-visible:ring-offset-2 focus-visible:ring-offset-linen"
            }
          />
        </label>
        <Button onClick={handleUpload} disabled={uploading || !file}>
          {uploading ? (
            <>
              <ContourProgress size={16} label="Uploading" />
              Uploading…
            </>
          ) : (
            "Upload"
          )}
        </Button>
      </div>

      {error ? (
        <p role="alert" className="mt-3 border border-ink bg-ink/5 px-3 py-2 text-sm text-ink">
          {error}
        </p>
      ) : null}
    </div>
  );
}
