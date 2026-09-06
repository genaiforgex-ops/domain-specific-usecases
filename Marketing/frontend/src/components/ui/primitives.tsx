import { type ReactNode, type CSSProperties, type InputHTMLAttributes, type TextareaHTMLAttributes, forwardRef } from 'react';
import { cn } from '../../lib/cn';
import { initials } from '../../lib/roles';

// ----- Card --------------------------------------------------------------
export function Card({
  className,
  children,
  as: As = 'div',
  ...rest
}: { className?: string; children: ReactNode; as?: any } & Record<string, unknown>) {
  return (
    <As
      className={cn(
        'rounded-lg bg-bg-tertiary border border-separator shadow-card',
        className,
      )}
      {...rest}
    >
      {children}
    </As>
  );
}

// ----- Badge / count -----------------------------------------------------
export function CountBadge({ n, tone = 'accent' }: { n: number; tone?: 'accent' | 'error' }) {
  if (!n) return null;
  return (
    <span
      className={cn(
        'inline-flex min-w-[18px] h-[18px] px-1 items-center justify-center rounded-full text-caption2 font-bold text-[color:var(--color-on-accent)] tabular-nums',
        tone === 'accent' ? 'bg-accent' : 'bg-error',
      )}
    >
      {n}
    </span>
  );
}

// ----- Pill / chip (meaning never on color alone — always has a label) ---
export function Pill({
  children,
  hue,
  className,
  icon,
}: {
  children: ReactNode;
  hue?: string;
  className?: string;
  icon?: ReactNode;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 h-6 px-2.5 rounded-full text-caption font-semibold whitespace-nowrap',
        className,
      )}
      style={
        hue
          ? { color: hue, backgroundColor: `color-mix(in srgb, ${hue} 14%, transparent)` }
          : { color: 'var(--color-label-secondary)', backgroundColor: 'var(--color-fill-quaternary)' }
      }
    >
      {icon}
      {children}
    </span>
  );
}

// ----- Avatar ------------------------------------------------------------
export function Avatar({ name, ring, size = 32 }: { name: string; ring?: string; size?: number }) {
  return (
    <span
      className="inline-flex items-center justify-center rounded-full font-semibold text-white shrink-0"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.38,
        background: `linear-gradient(135deg, ${ring ?? '#8e8e93'}, color-mix(in srgb, ${ring ?? '#8e8e93'} 55%, #000))`,
        boxShadow: ring ? `0 0 0 2px var(--color-bg), 0 0 0 3.5px ${ring}40` : undefined,
      }}
      aria-hidden
    >
      {initials(name)}
    </span>
  );
}

// ----- Input / Textarea --------------------------------------------------
export const Field = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement> & { label?: string; hint?: string }
>(({ label, hint, className, id, ...rest }, ref) => (
  <label className="block">
    {label && <span className="block mb-1.5 text-footnote font-semibold text-label-secondary">{label}</span>}
    <input
      ref={ref}
      id={id}
      className={cn(
        'w-full h-11 px-3.5 rounded-md bg-bg-secondary border border-separator text-body text-label',
        'placeholder:text-label-tertiary focus-ring transition-shadow duration-fast',
        className,
      )}
      {...rest}
    />
    {hint && <span className="block mt-1 text-caption text-label-tertiary">{hint}</span>}
  </label>
));
Field.displayName = 'Field';

export const Area = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string }
>(({ label, className, ...rest }, ref) => (
  <label className="block">
    {label && <span className="block mb-1.5 text-footnote font-semibold text-label-secondary">{label}</span>}
    <textarea
      ref={ref}
      className={cn(
        'w-full min-h-[88px] p-3.5 rounded-md bg-bg-secondary border border-separator text-body text-label',
        'placeholder:text-label-tertiary focus-ring resize-y transition-shadow duration-fast',
        className,
      )}
      {...rest}
    />
  </label>
));
Area.displayName = 'Area';


// ----- Empty state (an invitation to act) --------------------------------
export function EmptyState({
  icon,
  title,
  body,
  action,
  compact,
}: {
  icon?: ReactNode;
  title: string;
  body: string;
  /** Optional call-to-action (button/link) shown below the copy. */
  action?: ReactNode;
  /** Tighter type + spacing for use inside a card or dropdown. */
  compact?: boolean;
}) {
  return (
    <div className={cn('flex flex-col items-center justify-center text-center', compact ? 'py-8 px-4' : 'py-12 px-6')}>
      {icon && <div className={cn('text-label-tertiary', compact ? 'mb-2' : 'mb-3')}>{icon}</div>}
      <p className={cn('text-label', compact ? 'text-footnote font-semibold' : 'text-headline')}>{title}</p>
      <p className={cn('text-label-secondary max-w-sm', compact ? 'mt-0.5 text-caption' : 'mt-1 text-subheadline')}>{body}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

// ----- Skeleton (perceived-performance placeholder) ----------------------
// A neutral block with a slow light-sweep for content that's still loading.
// Compose these to mirror the shape of the real content (a title line, a row,
// a card) so the layout doesn't jump when data arrives.
export function Skeleton({ className, style }: { className?: string; style?: CSSProperties }) {
  return <span className={cn('skeleton block', className)} style={style} aria-hidden />;
}
