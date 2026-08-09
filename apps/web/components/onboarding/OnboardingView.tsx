"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";

const OnboardingTerrain = dynamic(
  () => import("./OnboardingTerrain").then((m) => m.OnboardingTerrain),
  { ssr: false, loading: () => <div className="h-full w-full animate-pulse bg-ink/5" aria-hidden /> },
);

/**
 * The workspace onboarding moment. Creating a workspace: the terrain rises from
 * flat — "your knowledge landscape doesn't exist yet, it's about to." Joining via
 * invite: the terrain is already formed with a marker at your position — "you're
 * joining an existing map." Mode from ?mode=join.
 */
export function OnboardingView() {
  const params = useSearchParams();
  const joining = params.get("mode") === "join";

  return (
    <main className="min-h-screen p-3 sm:p-5">
      <div className="neatline flex min-h-[calc(100vh-1.5rem)] flex-col sm:min-h-[calc(100vh-2.5rem)]">
        <header className="flex items-center gap-2 px-6 py-4">
          <span aria-hidden className="text-pewter">
            ◈
          </span>
          <span className="font-mono text-sm uppercase tracking-cartouche text-ink">AtlasKB</span>
        </header>

        <div className="flex flex-1 flex-col items-center justify-center gap-6 px-6 text-center">
          <div>
            <p className="marginalia text-[0.7rem] uppercase tracking-cartouche text-graphite">
              {joining ? "Joining a survey" : "Beginning a survey"}
            </p>
            <h1 className="mt-1 font-display text-3xl font-medium text-ink sm:text-4xl">
              {joining ? "You're joining an existing map" : "Your knowledge landscape"}
            </h1>
            <p className="mt-2 max-w-md text-sm text-graphite">
              {joining
                ? "The territory is already charted — your marker has been placed."
                : "It doesn't exist yet. As you upload documents, hills and valleys will rise."}
            </p>
          </div>
          <div className="h-[360px] w-full max-w-2xl overflow-hidden rounded-lg border border-graphite/25 bg-ink/[0.03]">
            <OnboardingTerrain joining={joining} />
          </div>
        </div>
      </div>
    </main>
  );
}
