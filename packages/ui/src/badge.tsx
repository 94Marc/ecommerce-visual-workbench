import type { HTMLAttributes } from "react";

import { cn } from "./utils";

export function Badge({className, ...props}: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-[#d9dfe9] bg-white px-2.5 py-1 text-[11px] font-bold tracking-wide text-[#526078]",
        className,
      )}
      {...props}
    />
  );
}
