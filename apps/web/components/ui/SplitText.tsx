"use client";

// In-house SplitText: splits a heading into per-letter spans that rise+fade in
// with a stagger on load. Rebuilt from scratch in the token system (npm/React
// Bits unavailable). Technique — staggered per-glyph reveal — is the standard
// SplitText pattern; reduced-motion shows the text statically (see globals.css).
export function SplitText({
  text,
  className = "",
  stagger = 0.03,
  duration = 0.5,
}: {
  text: string;
  className?: string;
  stagger?: number;
  duration?: number;
}) {
  return (
    <span className={className} aria-label={text}>
      {text.split("").map((ch, i) => (
        <span
          key={i}
          aria-hidden
          className="split-letter inline-block"
          style={{
            opacity: 0,
            animation: `split-in ${duration}s cubic-bezier(0.16,1,0.3,1) ${i * stagger}s forwards`,
            whiteSpace: ch === " " ? "pre" : undefined,
          }}
        >
          {ch === " " ? " " : ch}
        </span>
      ))}
    </span>
  );
}
