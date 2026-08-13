import Link from "next/link";

import {
  AGENT_MAX_ITERATIONS,
  AGENT_NODES,
  CACHE_NOTE,
  COST_NOTES,
  LANDMARKS,
  LATENCY_NOTE,
  LATENCY_ROWS,
  QUALITY_NOTE,
  QUALITY_STATS,
  STEPS,
  TOOLKIT,
} from "@/lib/how-it-works-content";

import { AgentLoopInteractive } from "./AgentLoopInteractive";
import { ArchitectureDiagram } from "./ArchitectureDiagram";
import { DemoLivingAtlas } from "./DemoLivingAtlas";
import { RaceVisualization } from "./RaceVisualization";
import { Reveal } from "./Reveal";
import { RailItem, SectionRail } from "./SectionRail";

const RAIL_ITEMS: RailItem[] = [
  { id: "s0", label: "Opening" },
  { id: "s1", label: "What it does" },
  { id: "s2", label: "Architecture" },
  { id: "s3", label: "Step by step" },
  { id: "s4", label: "Agent loop" },
  { id: "s5", label: "Results" },
  { id: "s6", label: "Built with" },
  { id: "s7", label: "Explore" },
];

/**
 * The whole page — a single, calm, content-forward reading path. Earlier
 * drafts tried to stage this as a pinned-scroll 3D/parallax "journey"; that
 * depended on illustration assets that never arrived in a usable state and
 * added real complexity (a GSAP scroll rig, WebGL, an image pipeline) for a
 * background that was never the point. Everything that actually mattered —
 * the real Living Atlas embed, the real measured-number race, the real
 * interactive agent loop — needs none of that, so this drops it entirely and
 * puts the design effort into typography, rhythm, and those three pieces.
 */
export function HowItWorksContent() {
  return (
    <div className="bg-chart-navy">
      <SectionRail items={RAIL_ITEMS} />

      {/* 00 — Opening */}
      <section id="s0" className="relative overflow-hidden px-6 pb-28 pt-20 sm:px-10 sm:pt-28">
        <BigNumeral>00</BigNumeral>
        <div className="relative mx-auto max-w-3xl">
          <Reveal>
            <p className="marginalia text-[0.7rem] uppercase tracking-cartouche text-brass">
              How it works
            </p>
            <h1 className="mt-5 font-display text-5xl font-medium leading-[1.05] text-parchment sm:text-6xl">
              Here&rsquo;s the real system —
              <br className="hidden sm:block" /> end to end, no marketing gloss.
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-parchment/75">
              What actually happens, step by step, when someone asks AtlasKB a
              question: how the request is authorized, how the agent decides
              what to retrieve, and what it costs and takes to run.
            </p>
            <p className="mt-3 max-w-xl font-mono text-xs uppercase tracking-cartouche text-verdigris">
              Every number below is measured, not estimated.
            </p>
          </Reveal>
        </div>
      </section>

      {/* 01 — What it does */}
      <Section id="s1" n="01" kicker="What it does" title="Grounded answers, or an honest no." band>
        <Reveal>
          <p className="max-w-xl text-base leading-relaxed text-parchment/80">
            Answers are generated <em>only</em> from chunks the system actually
            retrieved — never from the model&rsquo;s general knowledge. Every claim
            in an answer maps back to the specific chunk ID(s) that support
            it. If nothing relevant turns up, the agent says so
            (&ldquo;cannot answer from the available documents&rdquo;) instead
            of guessing.
          </p>
          <div className="mt-8 max-w-xl">
            <DemoLivingAtlas />
          </div>
        </Reveal>
      </Section>

      {/* 02 — Architecture as landmarks */}
      <Section id="s2" n="02" kicker="Architecture" title="The system, mapped out." wide>
        <Reveal>
          <p className="max-w-2xl text-base leading-relaxed text-parchment/80">
            Every piece of the stack has a place on the map — and a real edge
            to the next stop, not just a box on a diagram.
          </p>
        </Reveal>
        <Reveal className="mt-8">
          <ArchitectureDiagram landmarks={LANDMARKS} />
        </Reveal>
        <div className="mt-10 grid gap-px overflow-hidden rounded-sm border border-graphite/20 bg-graphite/20 sm:grid-cols-2">
          {LANDMARKS.map((l) => (
            <Reveal key={l.id}>
              <div className="h-full bg-chart-navy p-6 transition-colors hover:bg-deep-chart/60">
                <p className="font-mono text-[0.65rem] uppercase tracking-cartouche text-brass">
                  {l.subtitle}
                </p>
                <p className="mt-1.5 font-display text-xl text-parchment">{l.name}</p>
                <p className="mt-2 text-sm leading-relaxed text-parchment/70">{l.detail}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* 03 — Step by step */}
      <Section id="s3" n="03" kicker="Step by step" title="From upload to cited answer." band>
        <ol className="relative mt-2 flex flex-col">
          <span
            aria-hidden
            className="absolute bottom-6 left-[0.95rem] top-6 hidden w-px bg-gradient-to-b from-brass/50 via-graphite/25 to-transparent sm:block"
          />
          {STEPS.map((s, i) => (
            <Reveal key={s.id}>
              <li
                className={`relative flex gap-6 py-6 ${i > 0 ? "border-t border-graphite/15 sm:border-t-0" : ""}`}
              >
                <span
                  aria-hidden
                  className="relative z-10 hidden h-8 w-8 shrink-0 items-center justify-center rounded-full border border-brass/50 bg-chart-navy font-mono text-xs text-brass sm:flex"
                >
                  {s.n}
                </span>
                <span className="font-display text-3xl text-brass/50 sm:hidden">{String(s.n).padStart(2, "0")}</span>
                <div>
                  <p className="font-display text-xl text-parchment">{s.title}</p>
                  <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-parchment/70">{s.body}</p>
                </div>
              </li>
            </Reveal>
          ))}
        </ol>
      </Section>

      {/* 04 — Inside the agent loop */}
      <Section id="s4" n="04" kicker="The agent loop" title="Bounded, so it never runs away." wide>
        <Reveal>
          <p className="max-w-2xl text-base leading-relaxed text-parchment/80">
            Four nodes, one conditional loop, hard-capped at{" "}
            <strong className="text-brass">{AGENT_MAX_ITERATIONS} iterations</strong>
            . If the agent still doesn&rsquo;t have enough by then, it answers with
            what it has rather than looping forever.
          </p>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-parchment/60">{CACHE_NOTE}</p>
        </Reveal>
        <Reveal className="mt-8 max-w-xl rounded-sm border border-graphite/20 bg-deep-chart/30 p-6">
          <AgentLoopInteractive />
        </Reveal>
        <div className="mt-10 grid gap-px overflow-hidden rounded-sm border border-graphite/20 bg-graphite/20 sm:grid-cols-2 lg:grid-cols-4">
          {AGENT_NODES.map((n, i) => (
            <Reveal key={n.id}>
              <div className="h-full bg-chart-navy p-5">
                <p className="font-mono text-[0.62rem] uppercase tracking-cartouche text-verdigris">
                  {String(i + 1).padStart(2, "0")}
                </p>
                <p className="mt-1.5 font-display text-lg text-parchment">{n.label}</p>
                <p className="mt-2 text-sm leading-relaxed text-parchment/70">{n.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
        <Reveal>
          <p className="mt-6 font-mono text-xs uppercase tracking-cartouche text-graphite">
            assess → plan, looped, until sufficient or {AGENT_MAX_ITERATIONS} iterations reached → generate
          </p>
        </Reveal>
      </Section>

      {/* 05 — Measured results */}
      <Section id="s5" n="05" kicker="Measured results" title="Real numbers, not estimates." band>
        <Reveal>
          <RaceVisualization />
        </Reveal>
        <Reveal>
          <div className="mt-12 grid grid-cols-2 gap-6 sm:grid-cols-5">
            {QUALITY_STATS.map((s) => (
              <div key={s.id}>
                <p className="marginalia text-3xl text-parchment sm:text-4xl">
                  {s.note ?? `${s.value}${s.suffix ?? ""}`}
                </p>
                <p className="mt-1 text-xs uppercase tracking-cartouche text-graphite">{s.label}</p>
              </div>
            ))}
          </div>
          <p className="mt-4 text-xs text-graphite">{QUALITY_NOTE}</p>
        </Reveal>

        <Reveal>
          <div className="mt-12 overflow-x-auto rounded-sm border border-graphite/20">
            <table className="marginalia w-full min-w-[480px] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-graphite/20 bg-deep-chart/40 text-xs uppercase tracking-cartouche text-graphite">
                  <th className="py-2.5 pl-4 pr-4 font-normal">Path</th>
                  <th className="py-2.5 pr-4 font-normal">p50</th>
                  <th className="py-2.5 pr-4 font-normal">p95</th>
                  <th className="py-2.5 pr-4 font-normal">Throughput</th>
                  <th className="py-2.5 pr-4 font-normal">Cache hit</th>
                </tr>
              </thead>
              <tbody>
                {LATENCY_ROWS.map((r) => (
                  <tr key={r.id} className="border-b border-graphite/10 text-parchment/85 last:border-0">
                    <td className="py-2.5 pl-4 pr-4">{r.path}</td>
                    <td className="py-2.5 pr-4 text-brass">{r.p50}</td>
                    <td className="py-2.5 pr-4">{r.p95}</td>
                    <td className="py-2.5 pr-4">{r.throughput}</td>
                    <td className="py-2.5 pr-4">{r.cacheHit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-4 max-w-xl text-sm leading-relaxed text-parchment/70">{LATENCY_NOTE}</p>
        </Reveal>

        <Reveal>
          <ul className="mt-10 flex flex-col gap-2">
            {COST_NOTES.map((c, i) => (
              <li key={i} className="flex gap-2 text-sm leading-relaxed text-parchment/70">
                <span aria-hidden className="text-brass">
                  ·
                </span>
                {c}
              </li>
            ))}
          </ul>
        </Reveal>
      </Section>

      {/* 06 — Built with */}
      <Section id="s6" n="06" kicker="Built with" title="The toolkit." wide>
        {(["Backend", "Frontend", "Tooling"] as const).map((group) => (
          <Reveal key={group}>
            <div className="mt-8 first:mt-0">
              <p className="font-mono text-[0.65rem] uppercase tracking-cartouche text-verdigris">
                {group}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {TOOLKIT.filter((t) => t.group === group).map((t) => (
                  <span
                    key={t.id}
                    className="rounded-sm border border-graphite/25 border-l-2 border-l-brass/60 bg-deep-chart/40 px-3 py-1.5 font-mono text-xs text-parchment/80 transition-colors hover:border-brass/60 hover:bg-deep-chart/70 hover:text-parchment"
                  >
                    {t.label}
                  </span>
                ))}
              </div>
            </div>
          </Reveal>
        ))}
      </Section>

      {/* 07 — Closing */}
      <section id="s7" className="relative overflow-hidden px-6 py-32 sm:px-10">
        <BigNumeral>07</BigNumeral>
        <div className="relative mx-auto max-w-3xl">
          <Reveal>
            <p className="marginalia text-[0.7rem] uppercase tracking-cartouche text-brass">
              That&rsquo;s the whole system
            </p>
            <h2 className="mt-4 font-display text-4xl font-medium leading-tight text-parchment sm:text-5xl">
              No gloss, just the machine.
            </h2>
            <div className="mt-10 flex flex-wrap items-center gap-8">
              <Link
                href="/chat"
                className="group inline-flex items-center gap-2 border-b border-brass pb-1 font-mono text-sm uppercase tracking-cartouche text-parchment transition-colors hover:border-parchment focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass"
              >
                Explore the live Atlas
                <span aria-hidden className="transition-transform duration-300 group-hover:translate-x-1">
                  →
                </span>
              </Link>
              <a
                href="https://github.com"
                className="text-sm text-graphite transition-colors hover:text-parchment focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass"
              >
                Run it yourself (GitHub · Quickstart)
              </a>
            </div>
          </Reveal>
        </div>
      </section>
    </div>
  );
}

/** A large, quiet section numeral — the editorial-page cue that replaces the
 *  old illustrated background. Pure type, no asset. */
function BigNumeral({ children }: { children: React.ReactNode }) {
  return (
    <span
      aria-hidden
      className="pointer-events-none absolute -top-6 right-4 select-none font-display text-[9rem] font-medium leading-none text-parchment/[0.04] sm:right-10 sm:text-[13rem]"
    >
      {children}
    </span>
  );
}

function Section({
  id,
  n,
  kicker,
  title,
  wide = false,
  band = false,
  children,
}: {
  id: string;
  n: string;
  kicker: string;
  title: string;
  wide?: boolean;
  band?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className={`relative overflow-hidden ${band ? "bg-deep-chart/30" : ""}`}>
      <BigNumeral>{n}</BigNumeral>
      <div className={`relative mx-auto ${wide ? "max-w-4xl" : "max-w-3xl"} px-6 py-24 sm:px-10`}>
        <Reveal>
          <p className="marginalia text-[0.7rem] uppercase tracking-cartouche text-brass">
            {n} — {kicker}
          </p>
          <h2 className="mt-3 font-display text-3xl font-medium leading-tight text-parchment sm:text-4xl">
            {title}
          </h2>
        </Reveal>
        <div className="mt-10">{children}</div>
      </div>
    </section>
  );
}
