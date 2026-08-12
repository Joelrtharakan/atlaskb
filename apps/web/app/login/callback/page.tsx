import { Suspense } from "react";

import { OIDCCallback } from "@/components/auth/OIDCCallback";
import { ContourProgress } from "@/components/ui/ContourProgress";

export default function LoginCallbackPage() {
  return (
    <Suspense fallback={<ContourProgress size={40} label="Loading" />}>
      <OIDCCallback />
    </Suspense>
  );
}
