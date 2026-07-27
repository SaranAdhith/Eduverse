import { cn } from "@/lib/utils";

// Eduverse brand mark: an orbit — a learner (center) circled by a topic on its
// path — set in a gradient tile. Evokes the "adaptive learning universe".
export function LogoMark({
  className,
  style,
}: {
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center rounded-[30%] bg-brand-gradient text-white shadow-glow",
        className,
      )}
      style={style}
      aria-hidden
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        className="h-[62%] w-[62%]"
        stroke="currentColor"
      >
        <ellipse
          cx="12"
          cy="12"
          rx="9"
          ry="4.4"
          transform="rotate(-32 12 12)"
          strokeWidth="1.6"
          opacity="0.9"
        />
        <circle cx="12" cy="12" r="3.1" fill="currentColor" stroke="none" />
        <circle cx="19.2" cy="7.6" r="1.7" fill="currentColor" stroke="none" />
      </svg>
    </span>
  );
}

// The full logo: mark + wordmark. `size` controls the mark; the wordmark scales
// with it. Optionally render just the mark.
export function Logo({
  className,
  size = 32,
  showText = true,
  gradient = false,
}: {
  className?: string;
  size?: number;
  showText?: boolean;
  gradient?: boolean;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark style={{ width: size, height: size }} className="" />
      {showText ? (
        <span
          className={cn(
            "font-display text-[1.35rem] font-semibold lowercase tracking-tight",
            gradient && "text-gradient",
          )}
        >
          eduverse
        </span>
      ) : null}
    </span>
  );
}
