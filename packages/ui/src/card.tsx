import type { HTMLAttributes } from "react";

import { cn } from "./utils";

export function Card({className, ...props}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-2xl border border-[#dfe4ec] bg-white shadow-[0_10px_35px_rgba(24,32,51,.05)]", className)}
      {...props}
    />
  );
}

