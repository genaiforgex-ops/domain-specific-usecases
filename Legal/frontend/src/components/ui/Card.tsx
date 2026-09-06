import type { ReactNode } from "react";

import { classNames } from "@/lib/utils";

export function Card({
  children,
  className,
  title,
  subtitle,
  actions,
}: {
  children: ReactNode;
  className?: string;
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div
      className={classNames(
        "bg-paper rounded-lg border border-separator/45 shadow-card",
        className,
      )}
    >
      {(title || actions) && (
        <div className="px-5 py-4 border-b border-separator/35 flex items-start justify-between gap-4">
          <div>
            {title && <h3 className="font-display text-title-3 text-label tracking-tight">{title}</h3>}
            {subtitle && <p className="text-subheadline text-label-secondary mt-0.5">{subtitle}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className="px-5 py-4">{children}</div>
    </div>
  );
}
