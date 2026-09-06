import { useMemo, useState, type CSSProperties, type ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';
import { cn } from '../../lib/cn';

/**
 * A Monday.com-style board: each group is its own bordered block with a thick
 * rounded colour bar down the left, a full cell grid (vertical + horizontal
 * lines) and solid status cells that fill edge to edge. Built as real <table>s
 * for alignment + a11y, each in its own horizontal scroller so narrow
 * viewports never break the page layout.
 */

export interface Column<T> {
  key: string;
  header: ReactNode;
  /** colgroup width, e.g. '160px'. Omit for the flexible column. */
  width?: string;
  align?: 'left' | 'center' | 'right';
  cell: (row: T) => ReactNode;
  /** Paint the whole cell (solid status/stage columns). */
  cellStyle?: (row: T) => CSSProperties | undefined;
  cellClassName?: string;
  headClassName?: string;
  /** Hide the column below this breakpoint to keep small screens legible. */
  hideBelow?: 'sm' | 'md' | 'lg';
}

export interface TableGroup<T> {
  id: string;
  label: string;
  /** Group accent — colours the title, the left bar and the row rail. */
  hue: string;
  rows: T[];
  /** Optional right-aligned summary shown in the group title (e.g. total ₹). */
  meta?: ReactNode;
}

const HIDE: Record<NonNullable<Column<unknown>['hideBelow']>, string> = {
  sm: 'hidden sm:table-cell',
  md: 'hidden md:table-cell',
  lg: 'hidden lg:table-cell',
};

const ALIGN = { left: 'text-left', center: 'text-center', right: 'text-right' } as const;

// Shared cell geometry — every cell carries a right + bottom hairline so the
// board reads as a spreadsheet grid, exactly like Monday.
const CELL = 'border-b border-r border-separator';

export function DataTable<T>({
  columns,
  groups,
  rowKey,
  onRowClick,
  minWidth = 720,
  empty,
  defaultCollapsed,
  hideGroupHeaders = false,
}: {
  columns: Column<T>[];
  groups: TableGroup<T>[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  minWidth?: number;
  empty?: ReactNode;
  /** Group ids that start collapsed. */
  defaultCollapsed?: string[];
  /** Hide the coloured group titles (used when a tab bar already scopes the view). */
  hideGroupHeaders?: boolean;
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set(defaultCollapsed ?? []));

  const toggleGroup = (id: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const total = useMemo(() => groups.reduce((n, g) => n + g.rows.length, 0), [groups]);
  if (total === 0 && empty) return <>{empty}</>;

  return (
    <div className="space-y-4">
      {groups.map((g) => {
        const isCollapsed = collapsed.has(g.id);

        return (
          <section key={g.id}>
            {/* Group title — sits above the block, in the group colour. */}
            {!hideGroupHeaders && (
              <button
                type="button"
                onClick={() => toggleGroup(g.id)}
                className="mb-2 flex items-center gap-1.5 rounded-md px-1 py-0.5 focus-ring"
                aria-expanded={!isCollapsed}
              >
                <ChevronRight
                  size={18}
                  className={cn('shrink-0 transition-transform duration-fast', !isCollapsed && 'rotate-90')}
                  style={{ color: g.hue }}
                />
                <span className="text-callout font-bold tracking-tight" style={{ color: g.hue }}>
                  {g.label}
                </span>
                <span className="text-footnote font-semibold text-label-tertiary tabular-nums">
                  {g.rows.length}
                </span>
                {g.meta && <span className="ml-1 text-caption text-label-tertiary">{g.meta}</span>}
              </button>
            )}

            {!isCollapsed && (
              <div className="flex overflow-hidden rounded-lg border border-separator bg-bg-tertiary shadow-card">
                {/* Thick rounded colour bar down the left of the whole block. */}
                <div className="w-1.5 shrink-0" style={{ background: g.hue }} aria-hidden />

                <div className="min-w-0 flex-1 overflow-x-auto">
                  <table className="w-full table-fixed border-collapse text-left" style={{ minWidth }}>
                    <colgroup>
                      {columns.map((c) => (
                        <col key={c.key} style={{ width: c.width }} />
                      ))}
                    </colgroup>

                    <thead>
                      <tr className="select-none bg-bg-secondary">
                        {columns.map((c) => (
                          <th
                            key={c.key}
                            scope="col"
                            className={cn(
                              'h-9 px-3 text-caption font-semibold uppercase tracking-wide text-label-tertiary',
                              CELL,
                              ALIGN[c.align ?? 'left'],
                              c.hideBelow && HIDE[c.hideBelow],
                              c.headClassName,
                            )}
                          >
                            {c.header}
                          </th>
                        ))}
                      </tr>
                    </thead>

                    <tbody className="align-middle">
                      {g.rows.map((row) => {
                        const k = rowKey(row);
                        return (
                          <tr
                            key={k}
                            onClick={onRowClick ? () => onRowClick(row) : undefined}
                            className={cn(
                              'transition-colors duration-fast',
                              onRowClick && 'hover:bg-fill-quaternary cursor-pointer',
                            )}
                          >
                            {columns.map((c) => {
                              const painted = c.cellStyle?.(row);
                              return (
                                <td
                                  key={c.key}
                                  className={cn(
                                    'h-12 px-3 text-footnote text-label',
                                    CELL,
                                    ALIGN[c.align ?? 'left'],
                                    c.hideBelow && HIDE[c.hideBelow],
                                    painted && 'text-center font-semibold text-white',
                                    c.cellClassName,
                                  )}
                                  style={painted}
                                >
                                  {c.cell(row)}
                                </td>
                              );
                            })}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
