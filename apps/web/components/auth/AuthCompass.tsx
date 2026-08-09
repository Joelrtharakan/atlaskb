"use client";

import { AtlasCanvas, CompassInstrument } from "@/components/atlas-world";

/**
 * The quietest 3D moment on the site: a modest brass compass beside the auth
 * form, needle drifting gently. No functional meaning — "finding your way in".
 * Deliberately smaller and calmer than the form it sits next to.
 */
export function AuthCompass() {
  return (
    <AtlasCanvas
      camera={{ position: [0, 0, 5], fov: 45 }}
      fallback={null}
      render={({ reducedMotion }) => (
        <CompassInstrument drift size={1.5} reducedMotion={reducedMotion} />
      )}
    />
  );
}
