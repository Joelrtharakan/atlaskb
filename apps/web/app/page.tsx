import AtlasBackdrop from "@/components/living-atlas/AtlasBackdrop";

/**
 * Landing page — "the plate".
 * A near-full-bleed ambient Living Atlas behind a map-sheet neatline, with copy
 * anchored to the left margin as a cartouche (title block). No centered hero,
 * no card, no gradient blob.
 */
export default function Home() {
  return (
    <main className="relative min-h-screen overflow-hidden p-3 sm:p-5">
      {/* Map-sheet neatline framing the whole viewport. */}
      <div className="neatline relative flex min-h-[calc(100vh-1.5rem)] flex-col sm:min-h-[calc(100vh-2.5rem)]">
        {/* The signature ambient field. */}
        <AtlasBackdrop />

        {/* Graticule tick, top-right corner. */}
        <div className="marginalia pointer-events-none absolute right-4 top-4 text-[0.7rem] tracking-cartouche">
          N ⌐
        </div>

        {/* Wordmark, top-left; auth links top-right. */}
        <header className="relative z-10 flex items-center justify-between gap-2 p-6">
          <div className="flex items-center gap-2">
            <span aria-hidden className="text-pewter">
              ◈
            </span>
            <span className="font-mono text-sm uppercase tracking-cartouche text-ink">AtlasKB</span>
          </div>
          <nav aria-label="Account" className="flex items-center gap-4 font-mono text-xs uppercase tracking-cartouche">
            <a
              href="/login"
              className="text-graphite hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter"
            >
              Log in
            </a>
            <a
              href="/signup"
              className="border-b border-pewter pb-0.5 text-ink hover:text-pewter focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter"
            >
              Sign up
            </a>
          </nav>
        </header>

        {/* Cartouche — the map's title block, anchored to the left margin. */}
        <div className="relative z-10 flex flex-1 items-center">
          <div className="max-w-md px-6 sm:px-10">
            <p className="marginalia mb-4 text-[0.7rem] uppercase tracking-cartouche text-pewter">
              Multi-tenant agentic RAG
            </p>
            <h1 className="font-display text-5xl font-medium leading-[1.05] text-ink sm:text-6xl">
              Chart your organization&rsquo;s knowledge.
            </h1>
            <p className="mt-5 max-w-sm text-base leading-relaxed text-graphite">
              Documents are territory. Every question surveys the map and lights a route to the
              places that answer you.
            </p>
            <a
              href="/documents"
              className="mt-8 inline-flex items-center gap-2 border-b border-pewter pb-1 font-mono text-sm uppercase tracking-cartouche text-ink transition-colors hover:text-pewter focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter"
            >
              Enter the atlas
              <span aria-hidden>&rarr;</span>
            </a>
          </div>
        </div>

        {/* Mono scale bar — real build metadata, surveyor's marginalia. */}
        <footer className="marginalia relative z-10 flex flex-wrap gap-x-4 gap-y-1 p-6 text-[0.7rem]">
          <span>status: scaffold</span>
          <span aria-hidden>·</span>
          <span>build 0.0.0</span>
          <span aria-hidden>·</span>
          <span>pg 15432</span>
          <span aria-hidden>·</span>
          <span>redis 6380</span>
        </footer>
      </div>
    </main>
  );
}
