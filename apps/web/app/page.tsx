import AtlasBackdrop from "@/components/living-atlas/AtlasBackdrop";

/**
 * Landing page — "the plate".
 * A centred, near-full-bleed ambient Living Atlas behind a map-sheet neatline.
 * A left scrim + soft vignette keep the cartouche legible over the field.
 */
export default function Home() {
  return (
    <main className="relative min-h-screen overflow-hidden p-3 sm:p-5">
      {/* Map-sheet neatline framing the whole viewport. */}
      <div className="neatline relative flex min-h-[calc(100vh-1.5rem)] flex-col overflow-hidden sm:min-h-[calc(100vh-2.5rem)]">
        {/* The signature ambient field (centred, full-bleed). */}
        <AtlasBackdrop />

        {/* Gentle left fade so any node drifting near the title block stays faint. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 z-[1]"
          style={{
            background:
              "linear-gradient(90deg, rgba(217,220,209,0.85) 0%, rgba(217,220,209,0.3) 18%, rgba(217,220,209,0) 34%)",
          }}
        />
        {/* Soft vignette to frame the field on the right. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 z-[1]"
          style={{
            background:
              "radial-gradient(90% 110% at 72% 50%, rgba(217,220,209,0) 55%, rgba(217,220,209,0.5) 100%)",
          }}
        />

        {/* Wordmark, top-left; auth links top-right. */}
        <header className="relative z-10 flex items-center justify-between gap-2 p-6">
          <div className="flex items-center gap-2">
            <span aria-hidden className="text-pewter">
              ◈
            </span>
            <span className="font-mono text-sm uppercase tracking-cartouche text-ink">AtlasKB</span>
          </div>
          <nav
            aria-label="Account"
            className="flex items-center gap-4 font-mono text-xs uppercase tracking-cartouche"
          >
            <a
              href="/login"
              className="text-graphite transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter"
            >
              Log in
            </a>
            <a
              href="/signup"
              className="border-b border-pewter pb-0.5 text-ink transition-colors hover:border-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter"
            >
              Sign up
            </a>
          </nav>
        </header>

        {/* Cartouche — the map's title block, anchored to the left margin. */}
        <div className="relative z-10 flex flex-1 items-center">
          <div className="max-w-md px-6 sm:px-10">
            <p className="marginalia mb-4 text-[0.7rem] uppercase tracking-cartouche text-graphite">
              Multi-tenant agentic RAG
            </p>
            <h1 className="font-display text-5xl font-medium leading-[1.03] text-ink sm:text-6xl">
              Chart your organization&rsquo;s knowledge.
            </h1>
            <p className="mt-5 max-w-sm text-base leading-relaxed text-graphite">
              Documents are territory. Every question surveys the map and lights a route to the
              places that answer you — with a citation for every claim.
            </p>
            <a
              href="/documents"
              className="group mt-8 inline-flex items-center gap-2 border-b border-pewter pb-1 font-mono text-sm uppercase tracking-cartouche text-ink transition-colors hover:border-ink hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter"
            >
              Enter the atlas
              <span aria-hidden className="transition-transform duration-300 group-hover:translate-x-1">
                &rarr;
              </span>
            </a>
          </div>
        </div>

        {/* Mono scale bar — surveyor's marginalia. */}
        <footer className="marginalia relative z-10 flex flex-wrap gap-x-4 gap-y-1 p-6 text-[0.7rem]">
          <span>hybrid retrieval</span>
          <span aria-hidden>·</span>
          <span>agentic citations</span>
          <span aria-hidden>·</span>
          <span>multi-tenant</span>
          <span aria-hidden>·</span>
          <span>pgvector · redis</span>
        </footer>
      </div>
    </main>
  );
}
