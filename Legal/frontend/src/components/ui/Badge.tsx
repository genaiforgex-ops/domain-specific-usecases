import type { ReactNode } from "react";

import { classNames } from "@/lib/utils";

export function Badge({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={classNames(
        "inline-flex items-center px-2 py-0.5 rounded-md text-caption font-medium border border-separator/45 bg-bg-secondary/60",
        className,
      )}
    >
      {children}
    </span>
  );
}
