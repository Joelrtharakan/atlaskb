import dynamic from "next/dynamic";

const HeroSurveyScene = dynamic(
  () => import("@/components/landing/HeroSurveyScene").then((m) => m.HeroSurveyScene),
  { ssr: false },
);

/**
 * Landing page — "the plate".
 * Solid chart-navy sheet under a map-sheet neatline, with a real terrain massif
 * on the right (elevation = document scale) instead of a generic AI node graph.
 * Navy scrims guarantee text contrast at every viewport width — all copy sits on
 * navy, never on the terrain or a light gradient.
 */
export default function Home() {
  return (
    <main className="relative min-h-screen overflow-hidden bg-chart-navy p-3 sm:p-5">
      {/* Map-sheet neatline framing the whole viewport. */}
      <div className="neatline relative flex min-h-[calc(100vh-1.5rem)] flex-col overflow-hidden sm:min-h-[calc(100vh-2.5rem)]">
        {/* The terrain massif: lower band on mobile (below the copy), right side on
            desktop — so text always sits on clean navy at any width. */}
        <div className="absolute inset-x-0 bottom-0 z-0 h-[46%] lg:inset-y-0 lg:left-auto lg:right-0 lg:h-auto lg:w-[64%]">
          <HeroSurveyScene />
        </div>

        {/* Navy scrim from the left → text always sits on solid navy, the terrain
            fades in on the right. Holds contrast at any width. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 z-[1]"
          style={{
            background:
              "linear-gradient(90deg, #0F1A24 0%, rgba(15,26,36,0.92) 34%, rgba(15,26,36,0.35) 55%, rgba(15,26,36,0) 72%)",
          }}
        />
        {/* Bottom + top navy scrims so the nav and the feature strip stay legible
            where they overlap the terrain. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 z-[1] h-32"
          style={{ background: "linear-gradient(0deg, #0F1A24 0%, rgba(15,26,36,0.65) 45%, rgba(15,26,36,0) 100%)" }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 z-[1] h-24"
          style={{ background: "linear-gradient(180deg, #0F1A24 0%, rgba(15,26,36,0.55) 50%, rgba(15,26,36,0) 100%)" }}
        />

        {/* Wordmark, top-left; auth links top-right. */}
        <header className="relative z-10 flex items-center justify-between gap-2 p-6">
          <div className="flex items-center gap-2.5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logomark.png" alt="" aria-hidden className="h-6 w-6" />
            <span className="font-mono text-sm uppercase tracking-cartouche text-parchment">
              AtlasKB
            </span>
          </div>
          <nav
            aria-label="Account"
            className="flex items-center gap-4 font-mono text-xs uppercase tracking-cartouche"
          >
            <a
              href="/login"
              className="text-graphite transition-colors hover:text-parchment focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass"
            >
              Log in
            </a>
            <a
              href="/signup"
              className="border-b border-brass pb-0.5 text-parchment transition-colors hover:border-parchment focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass"
            >
              Sign up
            </a>
          </nav>
        </header>

        {/* Cartouche — the map's title block, anchored to the left margin.
            Top-aligned on mobile (terrain sits below it), centered on desktop. */}
        <div className="pointer-events-none relative z-10 flex flex-1 items-start pt-[6vh] lg:items-center lg:pt-0">
          <div className="pointer-events-auto max-w-md px-6 sm:px-10">
            <p className="marginalia mb-4 text-[0.7rem] uppercase tracking-cartouche text-brass">
              Multi-tenant agentic RAG
            </p>
            <h1 className="font-display text-5xl font-medium leading-[1.03] text-parchment sm:text-6xl">
              Chart your organization&rsquo;s knowledge.
            </h1>
            <p className="mt-5 max-w-sm text-base leading-relaxed text-parchment/80">
              Documents are territory. Every question surveys the map and lights a route to the
              places that answer you — with a citation for every claim.
            </p>
            <a
              href="/documents"
              className="group mt-8 inline-flex items-center gap-2 border-b border-brass pb-1 font-mono text-sm uppercase tracking-cartouche text-parchment transition-colors hover:border-parchment focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass"
            >
              Enter the atlas
              <span aria-hidden className="transition-transform duration-300 group-hover:translate-x-1">
                &rarr;
              </span>
            </a>
          </div>
        </div>

        {/* Mono scale bar — surveyor's marginalia. */}
        <footer className="marginalia relative z-10 flex flex-wrap gap-x-4 gap-y-1 p-6 text-[0.7rem] text-graphite">
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
