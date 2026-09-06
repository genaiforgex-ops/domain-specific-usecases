import { type ReactNode } from 'react';
import { cn } from '../../lib/cn';

// One altitude: every page spends the full window width. No centred reading
// column, no capped deck — just a gutter that grows with the viewport so content
// keeps breathing room from the edge instead of running into it.
//
// The gutter steps 24 → 32 → 48 → 72px. The first three are project spacing
// tokens; the scale stops at 8 (=48px), so the widest step is written out rather
// than as `px-12`, which would fall back to Tailwind's default 3rem and collide
// with 48px — an `lg`/`2xl` pair that looked like it grew but didn't.
export function Page({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('w-full min-w-0 py-6 px-5 sm:px-6 lg:px-8 2xl:px-[72px]', className)}>
      {children}
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 mb-5">
      <div className="min-w-0">
        {eyebrow && <p className="text-footnote font-semibold text-label-secondary mb-0.5">{eyebrow}</p>}
        <h1 className="text-large-title font-bold tracking-tight text-sheen">{title}</h1>
        {subtitle && <p className="mt-1 text-callout text-label-secondary">{subtitle}</p>}
      </div>
      {actions && <div className="shrink-0 flex items-center gap-2 pt-1">{actions}</div>}
    </div>
  );
}
