// Cartography-flavored progress indicator: nested contour lines (like a
// topographic map) that ripple outward instead of a generic spinner. Rendered
// in quiet chrome colors (pewter/graphite) — no reserved state colors, since the
// document surfaces stay deliberately still (see design plan §6). With
// prefers-reduced-motion the rings simply hold as a static contour glyph.

type Props = {
  size?: number;
  className?: string;
  /** Accessible label; announced via an sr-only string. */
  label?: string;
};

const RINGS = [3, 6.5, 10, 13.5, 17];

export function ContourProgress({ size = 20, label, className = "" }: Props) {
  return (
    <span
      role="status"
      className={`inline-flex items-center ${className}`}
      style={{ width: size, height: size }}
    >
      <svg
        viewBox="0 0 40 40"
        width={size}
        height={size}
        aria-hidden="true"
        className="text-graphite"
      >
        {RINGS.map((r, i) => (
          <circle
            key={r}
            cx="20"
            cy="20"
            r={r}
            fill="none"
            stroke="currentColor"
            strokeWidth="1"
            className="contour-ring"
            style={{ animationDelay: `${i * 180}ms` }}
          />
        ))}
        <circle cx="20" cy="20" r="1.4" fill="currentColor" className="text-graphite" />
      </svg>
      {label ? <span className="sr-only">{label}</span> : null}
    </span>
  );
}
