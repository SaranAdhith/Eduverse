import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

// Square mono tags. Used sparingly — the design labels with kickers, not chips.
const badgeVariants = cva(
  "inline-flex items-center border px-2 py-0.5 font-mono text-2xs uppercase tracking-[0.12em]",
  {
    variants: {
      variant: {
        default: "border-accent-border bg-accent text-accent-foreground",
        secondary: "border-border bg-secondary text-muted-foreground",
        outline: "border-border-strong text-muted-foreground",
        success: "border-accent-border bg-accent text-accent-foreground",
        warning: "border-border-strong bg-muted text-warning",
        destructive: "border-destructive/40 bg-destructive-tint text-destructive",
        muted: "border-transparent bg-muted text-muted-foreground",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
