import {
  FilePlus, Send, ArrowRight, Sparkles, ShieldCheck, CheckCircle2,
  MessageSquareWarning, ImagePlus, ImageUp, Upload, Dot, Sliders, LayoutTemplate,
  PencilLine, Trash2,
} from 'lucide-react';
import { Card } from '../ui/primitives';
import { STAGES, ROLES, initials } from '../../lib/roles';
import { stageHue } from '../ui/cells';
import { timeAgo } from '../../lib/select';
import { cn } from '../../lib/cn';
import type { BriefEvent, BriefStage, RoleId } from '../../lib/types';

// ── Progress rail ────────────────────────────────────────────────────────────
// The same seven steps the table's StageDots count — the six pipeline stages plus
// the terminal `completed` — so the two never disagree about how long the chain is.
const RAIL: { id: BriefStage; label: string }[] = [
  ...STAGES.map((s) => ({ id: s.id as BriefStage, label: s.label })),
  { id: 'completed', label: 'Completed' },
];

// Where this brief sits in the chain, at a glance: draft → copywriting → approval
// → design. Past stages are filled+checked, the current one pulses.
export function BriefProgress({ stage }: Readonly<{ stage: BriefStage }>) {
  // A finished brief has no "in progress" step — every segment is full. Without
  // this, `completed` fell off the end of the old six-stage list and rendered an
  // entirely empty rail.
  const complete = stage === 'completed';
  const reached = RAIL.findIndex((r) => r.id === stage);
  const cleared = complete ? RAIL.length : Math.max(reached, 0);
  const current = complete ? -1 : reached;
  return (
    <ol className="flex items-stretch gap-1.5 w-full py-1" aria-label={`Pipeline — currently at ${stage}`}>
      {RAIL.map((s, i) => {
        const done = i < cleared;
        const active = i === current;
        const hue = stageHue(s.id);
        return (
          <li key={s.id} className="flex-1 min-w-0">
            <div className="relative h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--color-fill-quaternary)' }}>
              <div
                className="absolute inset-0 origin-left rounded-full transition-transform"
                style={{ background: hue, transform: `scaleX(${done ? 1 : active ? 0.55 : 0})` }}
              />
            </div>
            <div className="mt-1.5 flex items-center gap-1 min-w-0">
              <span
                className={cn('grid place-items-center rounded-full shrink-0', active ? 'h-3.5 w-3.5' : 'h-2.5 w-2.5')}
                style={{ background: done || active ? hue : 'var(--color-fill-quaternary)' }}
              />
              <span className={cn('truncate text-caption2 font-semibold', active ? 'text-label' : done ? 'text-label-secondary' : 'text-label-tertiary')}>
                {s.label}
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function Avatar({ role, name }: Readonly<{ role: RoleId; name: string }>) {
  return (
    <span
      className="grid place-items-center h-5 w-5 rounded-full text-caption2 font-bold text-white shrink-0"
      style={{ background: ROLES[role]?.accent ?? '#8e8e93' }}
    >
      {initials(name)}
    </span>
  );
}

// ── Activity timeline ────────────────────────────────────────────────────────
const KIND_ICON: Record<string, typeof Dot> = {
  created: FilePlus,
  edited: PencilLine,
  deleted: Trash2,
  submitted: Send,
  assigned: ArrowRight,
  creatives_generated: Sparkles,
  copies_submitted: Send,
  gate1_signoff: ShieldCheck,
  gate1_cleared: CheckCircle2,
  approved: CheckCircle2,
  changes_requested: MessageSquareWarning,
  banner_template_selected: LayoutTemplate,
  banner_images_generated: ImagePlus,
  banner_image_uploaded: ImageUp,
  banner_image_edited: Sliders,
  banner_images_approved: CheckCircle2,
  design_submitted: Send,
  figma_exported: Upload,
};
const SUCCESS_KINDS = new Set(['gate1_cleared', 'approved', 'banner_images_approved', 'figma_exported']);

function kindHue(kind: string): string {
  if (kind === 'changes_requested' || kind === 'deleted') return 'var(--color-error)';
  if (SUCCESS_KINDS.has(kind)) return 'var(--color-success)';
  return 'var(--color-accent)';
}

// The transparency feed: every state change, newest first, identity-stamped, with
// any change-request note shown inline.
export function BriefTimeline({ events }: Readonly<{ events: BriefEvent[] | null }>) {
  return (
    <Card className="p-5 flex flex-col h-[560px]">
      <p className="text-subheadline font-bold text-label mb-1 shrink-0">Activity</p>
      <p className="text-caption text-label-tertiary mb-4 shrink-0">Every step on this brief — who did what, when, and why.</p>

      {events === null ? (
        <div className="flex justify-center py-8">
          <span className="h-5 w-5 rounded-full border-2 border-separator border-t-accent animate-spin" aria-label="Loading" />
        </div>
      ) : events.length === 0 ? (
        <p className="text-footnote text-label-tertiary">No activity yet.</p>
      ) : (
        <ol className="relative flex-1 overflow-y-auto pr-1 -mr-1">
          {[...events].reverse().map((e, i, arr) => {
            const Icon = KIND_ICON[e.kind] ?? Dot;
            const hue = kindHue(e.kind);
            const last = i === arr.length - 1;
            return (
              <li key={e.id} className="relative flex gap-3 pb-4">
                {/* connector line */}
                {!last && <span className="absolute left-[15px] top-8 bottom-0 w-px bg-separator" aria-hidden />}
                <span
                  className="relative z-10 grid place-items-center h-8 w-8 rounded-full shrink-0"
                  style={{ background: `color-mix(in srgb, ${hue} 14%, transparent)`, color: hue }}
                >
                  <Icon size={15} />
                </span>
                <div className="min-w-0 flex-1 pt-0.5">
                  <p className="text-subheadline text-label">{e.action}</p>
                  <p className="text-caption text-label-tertiary mt-0.5">
                    <Avatar role={e.actor_role} name={e.actor_name} />
                    <span className="ml-1.5 align-middle">
                      {e.actor_name} · {ROLES[e.actor_role]?.title ?? e.actor_role} · {timeAgo(e.at)}
                    </span>
                  </p>
                  {e.note && (
                    <p className="mt-1.5 text-footnote text-label-secondary whitespace-pre-wrap rounded-md bg-bg-secondary border border-separator px-3 py-2">
                      “{e.note}”
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}
