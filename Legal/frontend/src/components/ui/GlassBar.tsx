import type { ReactNode } from "react";

import { classNames } from "@/lib/utils";

export function GlassBar({
  children,
  className,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "header" | "aside" | "nav";
}) {
  return (
    <Tag className={classNames("glass", className)}>
      {children}
    </Tag>
  );
}
