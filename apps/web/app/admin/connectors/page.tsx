import { Suspense } from "react";

import { ConnectorsView } from "@/components/admin/ConnectorsView";
import { AppShell } from "@/components/ui/AppShell";
import { ContourProgress } from "@/components/ui/ContourProgress";

export default function ConnectorsPage() {
  return (
    <AppShell>
      <Suspense fallback={<ContourProgress size={40} label="Loading" />}>
        <ConnectorsView />
      </Suspense>
    </AppShell>
  );
}
