import type { CSSProperties } from 'react';
import { FileText } from 'lucide-react';
import { Avatar } from './primitives';
import { STAGES, stageMeta } from '../../lib/roles';
import { timeAgo } from '../../lib/select';
import type { BriefStatus, Stage } from '../../lib/types';
import type { DesignStatus } from '../../lib/design';
import { DESIGN_STATUS } from '../../lib/design';

/* -------------------------------------------------------------------------
 * Solid-fill status/stage cells — a colour-coded board (Monday style). Each fill
 * is a self-contained mid-tone chosen to read two ways: white text sits on it in
 * the cell, and the same hue is legible as a group-title colour on both light and
 * dark boards. Meaning never rides on colour alone: every cell keeps its label.
 * ------------------------------------------------------------------------- */

// Shared mid-tone palette. Tuned so white text clears AA on the fill and the hue
// stays visible as text/accent on both light and dark page backgrounds.
const HUE = {
  slate: '#64748b',   // neutral / not-started / off
  blue: '#2563eb',    // pending / in-progress
  cyan: '#0e7490',    // early creative work
  violet: '#7c3aed',  // in review / ready
  orange: '#c2410c',  // needs attention / changes
  green: '#15803d',   // approved / done
} as const;
const colorFill = (hue: string): CSSProperties => ({ backgroundColor: hue, color: '#fff' });

// Neutral greyscale ramp — kept for ad-hoc boolean columns (active/priority)
// that are genuinely binary and shouldn't compete with the semantic hues.
// level 0 (lightest) → 4 (darkest)
const FILL = ['#8a8a90', '#70707a', '#5a5a62', '#46464d', '#313137'];
export const monoFill = (lvl: 0 | 1 | 2 | 3 | 4): CSSProperties => ({ backgroundColor: FILL[lvl], color: '#fff' });

export const STATUS_HUE: Record<BriefStatus, string> = {
  draft: HUE.slate,
  submitted: HUE.blue,
  changes_requested: HUE.orange,
  approved: HUE.green,
};
const STATUS_TEXT: Record<BriefStatus, string> = {
  draft: 'Draft',
  submitted: 'Pending approval',
  approved: 'Approved',
  changes_requested: 'Changes requested',
};
export const statusFill = (s: BriefStatus): CSSProperties => colorFill(STATUS_HUE[s]);
export const statusLabel = (s: BriefStatus) => STATUS_TEXT[s];

// Active/inactive toggle cells (e.g. admin user status) — green when on, neutral slate when off.
export const activeFill = (active: boolean): CSSProperties => colorFill(active ? HUE.green : HUE.slate);

// `STAGES` (roles.ts) only covers the six live pipeline stages; map every stage
// (incl. terminal/legacy ones) to a hue along the pipeline.
const STAGE_HUE: Partial<Record<Stage, string>> = {
  draft: HUE.slate, brief_review: HUE.blue, copywriting: HUE.cyan, design: HUE.violet,
  creative_review: HUE.orange, final_signoff: HUE.green, completed: HUE.green, approval: HUE.orange,
};
const EXTRA_LABEL: Partial<Record<Stage, string>> = { completed: 'Completed', approval: 'Approval' };
export const stageFill = (s: Stage): CSSProperties => colorFill(STAGE_HUE[s] ?? HUE.slate);
export const stageLabel = (s: Stage): string => EXTRA_LABEL[s] ?? stageMeta(s)?.label ?? s;
/** CSS colour string for a stage — usable as a group hue / rail. */
export const stageHue = (s: Stage): string => STAGE_HUE[s] ?? HUE.slate;

const DESIGN_HUE: Record<DesignStatus, string> = {
  not_started: HUE.slate, in_progress: HUE.blue, ready: HUE.violet, done: HUE.green,
};
export const designFill = (s: DesignStatus): CSSProperties => colorFill(DESIGN_HUE[s]);
export const designLabel = (s: DesignStatus) => DESIGN_STATUS[s].label;
/** Group-hue for a design status. */
export const designHue = (s: DesignStatus): string => DESIGN_HUE[s];

/* -------------------------------------------------------------------------
 * Cell content renderers — small, aligned building blocks for columns.
 * ------------------------------------------------------------------------- */

export function TitleCell({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="flex items-center gap-2.5 min-w-0">
      <span className="grid place-items-center h-7 w-7 rounded-md bg-bg-secondary text-label-secondary shrink-0">
        <FileText size={14} />
      </span>
      <div className="min-w-0">
        <p className="text-footnote font-semibold text-label truncate">{title}</p>
        {sub && <p className="text-caption2 text-label-tertiary truncate">{sub}</p>}
      </div>
    </div>
  );
}

export function OwnerCell({ name, ring }: { name?: string | null; ring?: string }) {
  if (!name) return <span className="text-caption text-label-tertiary">—</span>;
  return (
    <div className="flex items-center gap-2 min-w-0">
      <Avatar name={name} ring={ring} size={26} />
      <span className="text-footnote text-label-secondary truncate">{name}</span>
    </div>
  );
}

export function DateCell({ iso }: { iso?: string | null }) {
  if (!iso) return <span className="text-caption text-label-tertiary">—</span>;
  return <span className="text-footnote text-label-tertiary whitespace-nowrap">{timeAgo(iso)}</span>;
}

// The full seven-step chain for the dots: the six live pipeline stages plus the
// terminal `completed`. Derived from STAGES so adding a pipeline stage adds a dot
// (and widens the "n/7") on its own.
const DOT_STAGES: Stage[] = [...STAGES.map((s) => s.id), 'completed'];

/**
 * Pipeline progress as dots — one per step, filled up to and including the step
 * the brief has reached. The stage cell names *where* a brief is; this shows how
 * far along that is without reading the label.
 *
 * Counts the stage reached, so a fresh draft reads 1/7 and a finished brief 7/7,
 * climbing by one at every handoff.
 */
export function StageDots({ stage }: Readonly<{ stage: Stage }>) {
  const total = DOT_STAGES.length;
  // -1 only for the legacy `approval` alias, which is off this chain — it then
  // fills nothing rather than falsely claiming the first step.
  const reached = DOT_STAGES.indexOf(stage);
  const count = reached + 1;
  const label = `Step ${count} of ${total}`;

  return (
    <span className="inline-flex items-center gap-1.5 align-middle" title={label}>
      <span className="inline-flex items-center gap-1" aria-hidden>
        {DOT_STAGES.map((s, i) => {
          const filled = i <= reached;
          const active = i === reached;
          const hue = stageHue(s);
          return (
            <span
              key={s}
              className={`shrink-0 rounded-full ${active ? 'h-2.5 w-2.5' : 'h-2 w-2'}`}
              style={{
                background: filled ? hue : 'var(--color-fill-quaternary)',
                // A halo marks the step in flight, so "current" reads differently
                // from "already done" without relying on colour alone.
                boxShadow: active ? `0 0 0 2.5px ${hue}40` : undefined,
              }}
            />
          );
        })}
      </span>
      <span className="text-caption2 font-semibold text-label-tertiary tabular-nums whitespace-nowrap">
        {count}/{total}
      </span>
    </span>
  );
}
