import type { DocumentStatus } from "@/lib/types";

// The signature contour-ring badge: concentric survey rings whose color reads the
// state. Small inline SVG (not 3D) so it's cheap enough to repeat per row and is
// reused across Documents, Dashboard, and Chat citations for consistency.
const STATUS_COLOR: Record<DocumentStatus, string> = {
  ready: "#4A7C6F", // verdigris
  processing: "#C08A45", // brass
  failed: "#C1462F", // signal-red
};

export function ContourRing({
  status,
  size = 20,
}: {
  status: DocumentStatus;
  size?: number;
}) {
  const c = STATUS_COLOR[status];
  const r = size / 2;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden className="shrink-0">
      {[0.9, 0.62, 0.34].map((k, i) => (
        <circle
          key={i}
          cx={r}
          cy={r}
          r={r * k}
          fill="none"
          stroke={c}
          strokeWidth={1}
          opacity={0.45 + i * 0.2}
        />
      ))}
      <circle cx={r} cy={r} r={1.5} fill={c} />
    </svg>
  );
}
