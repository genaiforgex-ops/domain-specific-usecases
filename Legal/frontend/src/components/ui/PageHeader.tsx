import type { ReactNode } from "react";

import { classNames } from "@/lib/utils";

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
  className,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header
      className={classNames(
        "flex flex-col md:flex-row md:items-end md:justify-between gap-4 pb-2 animate-slide-up",
        className,
      )}
    >
      <div className="min-w-0">
        {eyebrow && (
          <div className="text-caption font-medium uppercase tracking-[0.16em] text-label-tertiary mb-2">
            {eyebrow}
          </div>
        )}
        <h1 className="font-display text-large-title text-label tracking-tight">{title}</h1>
        {subtitle && (
          <p className="mt-2 text-callout text-label-secondary max-w-2xl leading-relaxed">
            {subtitle}
          </p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2 shrink-0">{actions}</div>}
    </header>
  );
}
