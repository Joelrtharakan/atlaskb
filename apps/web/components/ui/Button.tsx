import { forwardRef, type ButtonHTMLAttributes } from "react";

type Variant = "solid" | "outline" | "ghost";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
};

// The only interactive accent is `pewter` (house metallic). Focus is always
// visible: a pewter ring offset against the linen paper.
const base =
  "inline-flex items-center justify-center gap-2 rounded-none border px-4 py-2 " +
  "font-mono text-sm uppercase tracking-cartouche transition-colors " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter " +
  "focus-visible:ring-offset-2 focus-visible:ring-offset-linen " +
  "disabled:cursor-not-allowed disabled:opacity-50";

const variants: Record<Variant, string> = {
  solid: "border-ink bg-ink text-linen hover:bg-graphite hover:border-graphite",
  outline: "border-pewter text-ink hover:bg-pewter/15",
  ghost: "border-transparent text-graphite hover:text-ink",
};

export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  { variant = "solid", className = "", type, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type ?? "button"}
      className={`${base} ${variants[variant]} ${className}`}
      {...props}
    />
  );
});
