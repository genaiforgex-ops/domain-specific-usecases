import { type ReactNode } from 'react';
import { Search } from 'lucide-react';
import { cn } from '../../lib/cn';

/**
 * The board's action row — title on the left, then optional search, filter chips
 * and primary actions. Sits above a DataTable and keeps every list page's chrome
 * consistent (echoing the reference board's toolbar).
 */
export function ListToolbar({
  title,
  subtitle,
  count,
  search,
  onSearch,
  searchPlaceholder = 'Search…',
  filters,
  actions,
}: {
  title: string;
  subtitle?: string;
  count?: number;
  search?: string;
  onSearch?: (v: string) => void;
  searchPlaceholder?: string;
  filters?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-start gap-x-4 gap-y-3">
      <div className="min-w-0">
        <div className="flex items-baseline gap-2 min-w-0">
          {/* Same size as PageHeader's title — a board is still a page, and its
              heading shouldn't shrink just because the toolbar sits beside it. */}
          <h1 className="text-large-title font-bold tracking-tight truncate text-sheen">{title}</h1>
          {count != null && (
            <span className="text-callout font-semibold text-label-tertiary tabular-nums">{count}</span>
          )}
        </div>
        {subtitle && <p className="mt-1 text-callout text-label-secondary">{subtitle}</p>}
      </div>

      <div className="flex flex-1 flex-wrap items-center justify-end gap-2 pt-1">
        {onSearch && (
          <div className="relative w-full sm:w-64">
            <Search
              size={15}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-label-tertiary pointer-events-none"
            />
            <input
              type="search"
              value={search ?? ''}
              onChange={(e) => onSearch(e.target.value)}
              placeholder={searchPlaceholder}
              className="w-full h-9 pl-9 pr-3 rounded-md bg-bg-tertiary border border-separator text-footnote text-label placeholder:text-label-tertiary outline-none focus-ring"
            />
          </div>
        )}
        {filters}
        {actions}
      </div>
    </div>
  );
}

export interface TabDef {
  id: string;
  label: string;
  count?: number;
  /** Optional accent dot colour, e.g. a status hue. */
  hue?: string;
}

/** Monday-style underline tabs — one active facet at a time. */
export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: TabDef[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="mb-4 flex items-center gap-1 border-b border-separator overflow-x-auto" role="tablist">
      {tabs.map((t) => {
        const on = t.id === active;
        return (
          <button
            key={t.id}
            role="tab"
            aria-selected={on}
            onClick={() => onChange(t.id)}
            className={cn(
              'relative flex items-center gap-2 h-9 px-3 -mb-px text-subheadline font-medium whitespace-nowrap border-b-2 transition-colors duration-fast focus-ring',
              on ? 'border-accent text-label' : 'border-transparent text-label-secondary hover:text-label',
            )}
          >
            {t.hue && <span className="h-2 w-2 rounded-full" style={{ background: t.hue }} aria-hidden />}
            {t.label}
            {t.count != null && (
              <span className={cn('text-caption font-semibold tabular-nums', on ? 'text-accent' : 'text-label-tertiary')}>
                {t.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** A single filter chip — toggles a facet on/off. */
export function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'h-9 px-3 rounded-md text-footnote font-medium whitespace-nowrap transition-colors duration-fast focus-ring border',
        active
          ? 'bg-accent-soft text-accent border-transparent'
          : 'bg-bg-tertiary text-label-secondary border-separator hover:text-label',
      )}
    >
      {children}
    </button>
  );
}
