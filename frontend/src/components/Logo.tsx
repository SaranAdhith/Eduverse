import { cn } from "@/lib/utils";

// The brand mark is a filled square — the same 13px block that opens the
// sidebar and the enrolment page. Flat and typographic, like the rest.
export function LogoMark({
  className,
  style,
}: {
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <span
      className={cn("inline-block shrink-0 bg-primary", className)}
      style={style}
      aria-hidden
    />
  );
}

// Mark + mono wordmark, letterspaced and uppercase.
export function Logo({
  className,
  size = 13,
  showText = true,
}: {
  className?: string;
  size?: number;
  showText?: boolean;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark style={{ width: size, height: size }} />
      {showText ? (
        <span className="font-mono text-xs uppercase tracking-[0.18em] text-muted-foreground">
          Eduverse
        </span>
      ) : null}
    </span>
  );
}
