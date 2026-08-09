import { Suspense } from "react";

import { OnboardingView } from "@/components/onboarding/OnboardingView";

export default function OnboardingPage() {
  return (
    <Suspense fallback={null}>
      <OnboardingView />
    </Suspense>
  );
}
