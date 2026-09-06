import { type ReactNode } from 'react';
import { Card } from '../ui/primitives';
import { cn } from '../../lib/cn';

// Shared building blocks for the role Home ("Today") screen. The whole point of
// Home is to answer two questions at a glance: what's going on, and what do I do
// next. These pieces keep that answer loud and consistent across every role.

// ----- Greeting ----------------------------------------------------------
export function Greeting({ name, role }: { name: string; role: string }) {
  const now = new Date();
  const hour = now.getHours();
  const part = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  const first = name.split(' ')[0] || name;
  const date = now.toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' });
  return (
    <div className="mb-6">
      <p className="text-caption font-semibold uppercase tracking-wider text-label-tertiary mb-1">
        {role} · {date}
      </p>
      <h1 className="text-large-title font-bold tracking-tight text-sheen">
        {part}, {first}
      </h1>
      <p className="mt-1 text-callout text-label-secondary">
        Here’s what’s on you right now, and what to do next.
      </p>
    </div>
  );
}

// ----- State strip: what's going on, in numbers --------------------------
export function StatGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">{children}</div>;
}

export function Stat({
  icon,
  label,
  value,
  accent,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  value: string | number;
  accent?: boolean;
  onClick?: () => void;
}) {
  const body = (
    <Card className={cn('p-4 h-full', accent && 'border-l-[3px] border-l-accent', onClick && 'hover:shadow-elevated transition-shadow duration-base')}>
      <div className="flex items-center justify-between text-label-tertiary mb-2">
        {icon}
        {accent ? <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden /> : null}
      </div>
      <p className="text-title-1 font-extrabold tracking-tight tabular-nums text-label">{value}</p>
      <p className="text-caption text-label-secondary mt-0.5">{label}</p>
    </Card>
  );
  return onClick ? (
    <button onClick={onClick} className="text-left focus-ring rounded-lg block">
      {body}
    </button>
  ) : (
    body
  );
}

// ----- Section header ----------------------------------------------------
export function HomeSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-6">
      <h2 className="text-headline text-label mb-3">{title}</h2>
      {children}
    </section>
  );
}

export function Loader() {
  return (
    <div className="flex justify-center py-16">
      <span className="h-6 w-6 rounded-full border-2 border-separator border-t-accent animate-spin" aria-label="Loading" />
    </div>
  );
}
