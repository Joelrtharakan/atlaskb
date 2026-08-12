"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { ContourProgress } from "@/components/ui/ContourProgress";
import { ApiError, api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { DocumentDetail, DocumentVersion } from "@/lib/types";

const ACCEPT = ".pdf,.md,.markdown,.html,.htm";

/**
 * A document's version history plus, for those who can manage it, a control to
 * re-upload new content. Re-uploading doesn't overwrite anything — it appends a
 * new version and re-points retrieval at it once ingestion succeeds, so this
 * list is the lineage: what changed, when, and which version is live now.
 */
export function VersionHistory({
  doc,
  onReuploaded,
}: {
  doc: DocumentDetail;
  onReuploaded: (doc: DocumentDetail) => void;
}) {
  const [versions, setVersions] = useState<DocumentVersion[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .documentVersions(doc.id)
      .then((r) => !cancelled && setVersions(r.versions))
      .catch((err) => {
        if (cancelled) return;
        setLoadError(
          err instanceof ApiError ? err.message : "Couldn't load version history.",
        );
      });
    return () => {
      cancelled = true;
    };
    // Re-fetch whenever the document's own status flips (e.g. reupload → ready).
  }, [doc.id, doc.status]);

  async function handleReupload() {
    if (!file) {
      setUploadError("Choose a replacement file first.");
      return;
    }
    setUploadError(null);
    setUploading(true);
    try {
      const updated = await api.reuploadDocument(doc.id, file);
      onReuploaded(updated);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    } catch (err) {
      setUploadError(
        err instanceof ApiError
          ? err.message
          : "The re-upload didn't reach the API. Check the backend is running and try again.",
      );
    } finally {
      setUploading(false);
    }
  }

  return (
    <div>
      <p className="marginalia text-[0.7rem] uppercase tracking-cartouche text-graphite">
        Version history
      </p>

      {loadError ? (
        <p role="alert" className="mt-2 border border-ink bg-ink/5 px-3 py-2 text-sm text-ink">
          {loadError}
        </p>
      ) : versions === null ? (
        <div className="mt-2 flex items-center gap-2 text-graphite">
          <ContourProgress size={16} label="Loading versions" />
          <span className="text-xs">Loading…</span>
        </div>
      ) : (
        <ul className="mt-2 flex flex-col gap-1.5">
          {versions.map((v) => (
            <li
              key={v.id}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-graphite/15 py-2 text-sm"
            >
              <span
                className={
                  v.is_current_version
                    ? "rounded-sm bg-verdigris/90 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-linen"
                    : "rounded-sm border border-graphite/40 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-cartouche text-graphite"
                }
              >
                {v.is_current_version ? "current" : `v${v.version_number}`}
              </span>
              {v.is_current_version ? (
                <span className="font-mono text-[10px] text-graphite">v{v.version_number}</span>
              ) : null}
              <span className="text-ink">{formatDateTime(v.created_at)}</span>
              <span className="font-mono text-[10px] uppercase tracking-cartouche text-graphite">
                {v.source ?? "upload"} · {v.chunk_count} chunks
              </span>
            </li>
          ))}
        </ul>
      )}

      {doc.can_manage_access ? (
        <div className="mt-4 border border-graphite/30 bg-linen/50 p-4">
          <p className="font-mono text-xs uppercase tracking-cartouche text-graphite">
            Re-survey this document
          </p>
          <p className="mt-1 text-sm text-graphite">
            Upload a new version of this file. If it&rsquo;s unchanged, nothing happens; otherwise
            it becomes the current version once it finishes surveying.
          </p>
          <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center">
            <label className="flex-1">
              <span className="sr-only">Choose a replacement file</span>
              <input
                ref={inputRef}
                type="file"
                accept={ACCEPT}
                onChange={(e) => {
                  setUploadError(null);
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
            <Button onClick={handleReupload} disabled={uploading || !file}>
              {uploading ? (
                <>
                  <ContourProgress size={16} label="Uploading" />
                  Uploading…
                </>
              ) : (
                "Re-upload"
              )}
            </Button>
          </div>
          {uploadError ? (
            <p role="alert" className="mt-3 border border-ink bg-ink/5 px-3 py-2 text-sm text-ink">
              {uploadError}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
