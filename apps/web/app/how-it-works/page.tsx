import type { Metadata } from "next";
import Link from "next/link";

import { HowItWorksContent } from "@/components/how-it-works/HowItWorksContent";

export const metadata: Metadata = {
  title: "How it works — AtlasKB",
  description:
    "A technical walkthrough of AtlasKB's architecture, agent loop, and measured results.",
};

export default function HowItWorksPage() {
  return (
    <main className="min-h-screen bg-chart-navy">
      <header className="relative z-10 mx-auto flex max-w-6xl items-center justify-between gap-2 p-6">
        <Link href="/" className="flex items-center gap-2.5">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logomark.png" alt="" aria-hidden className="h-6 w-6" />
          <span className="font-mono text-sm uppercase tracking-cartouche text-parchment">
            AtlasKB
          </span>
        </Link>
        <nav
          aria-label="Primary"
          className="flex items-center gap-4 font-mono text-xs uppercase tracking-cartouche"
        >
          <Link
            href="/how-it-works"
            aria-current="page"
            className="border-b border-brass pb-0.5 text-parchment"
          >
            How it works
          </Link>
          <Link
            href="/login"
            className="text-graphite transition-colors hover:text-parchment focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass"
          >
            Log in
          </Link>
          <Link
            href="/signup"
            className="border-b border-brass pb-0.5 text-parchment transition-colors hover:border-parchment focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass"
          >
            Sign up
          </Link>
        </nav>
      </header>

      <HowItWorksContent />

      <footer className="marginalia mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-1 px-6 py-8 text-[0.7rem] text-graphite">
        <span>AtlasKB</span>
        <span aria-hidden>·</span>
        <Link href="/" className="transition-colors hover:text-parchment">
          Home
        </Link>
        <span aria-hidden>·</span>
        <Link href="/how-it-works" className="transition-colors hover:text-parchment">
          How it works
        </Link>
        <span aria-hidden>·</span>
        <a
          href="https://github.com"
          className="transition-colors hover:text-parchment"
        >
          GitHub
        </a>
      </footer>
    </main>
  );
}
