import { CheckCircle2, LoaderCircle, Clock } from 'lucide-react';
import { Card } from '../ui/primitives';
import { STAGES, stageIndex, ROLES, initials } from '../../lib/roles';
import { stageHue } from '../ui/cells';
import { timeAgo } from '../../lib/select';
import { cn } from '../../lib/cn';
import type { Brief, BriefEvent, BriefStage, RoleId } from '../../lib/types';

// Which brief field carries the assigned person for each *stage*. Keyed by stage,
// not by role, because the Product Lead and the Marketing Lead each own two of
// them: the PL authors the brief (creator_id) and signs it off (product_id), the ML
// reviews the brief then the creative (both marketing_id). Keying this by role made
// every PL-owned row read `product_id`, so the brief's author was relabelled the
// moment sign-off was routed or reassigned to a different Product Lead. Mirrors the
// backend's REASSIGN_SLOTS and ReassignControl's HOLDER map.
const STAGE_ASSIGNEE: Partial<Record<BriefStage, keyof Brief>> = {
  draft: 'creator_id',
  brief_review: 'marketing_id',
  copywriting: 'copywriter_id',
  design: 'designer_id',
  creative_review: 'marketing_id',
  final_signoff: 'product_id',
};

// Who actually decided a checkpoint, once decided. The assignee columns are live —
// marketing_id is shared by both ML checkpoints and gets overwritten — so for a
// settled stage prefer the recorded decider: history shouldn't move under a
// reassignment.
const STAGE_DECIDER: Partial<Record<BriefStage, keyof Brief>> = {
  brief_review: 'brief_review_by_id',
  creative_review: 'creative_review_by_id',
  final_signoff: 'final_signoff_by_id',
};

// When a stage last moved, where the brief records it exactly. Copywriting and
// design have no such column and fall back to their owner's newest event.
const STAGE_AT: Partial<Record<BriefStage, keyof Brief>> = {
  draft: 'submitted_at',
  brief_review: 'brief_review_at',
  creative_review: 'creative_review_at',
  final_signoff: 'final_signoff_at',
};

type Status = 'done' | 'active' | 'waiting';
const STATUS_META: Record<Status, { label: string; icon: typeof CheckCircle2; hue: string }> = {
  done: { label: 'Done', icon: CheckCircle2, hue: 'var(--color-success)' },
  active: { label: 'In progress', icon: LoaderCircle, hue: 'var(--color-accent)' },
  waiting: { label: 'Waiting', icon: Clock, hue: 'var(--color-label-tertiary)' },
};

/**
 * The PMO view of a single brief: every stage of the pipeline, who owns it, who
 * is assigned, and whether it's done / active / still waiting. One clear answer
 * to "who is doing what right now" — replaces the old People + Assigned-team split.
 */
export function BriefOwnership({
  brief,
  events,
  people,
}: Readonly<{
  brief: Brief;
  events: BriefEvent[] | null;
  people: { id: string; full_name: string }[];
}>) {
  const current = stageIndex(brief.stage);
  const finished = brief.stage === 'completed';

  return (
    <Card className="p-5 flex flex-col h-[560px]">
      <p className="text-subheadline font-bold text-label mb-1 shrink-0">Who's doing what</p>
      <p className="text-caption text-label-tertiary mb-4 shrink-0">Owner and status for every stage of the pipeline.</p>

      <ol className="space-y-1.5 flex-1 overflow-y-auto pr-1 -mr-1">
        {STAGES.map((s, i) => {
          const status: Status = finished || i < current ? 'done' : i === current ? 'active' : 'waiting';
          // Every pipeline stage is owned by a real role (never AUTO/SYSTEM).
          const role = s.owner as RoleId;
          const stage = s.id as BriefStage;
          const decidedBy = STAGE_DECIDER[stage]
            ? (brief[STAGE_DECIDER[stage]!] as string | null)
            : null;
          const assignedTo = STAGE_ASSIGNEE[stage]
            ? (brief[STAGE_ASSIGNEE[stage]!] as string | null)
            : null;
          // Whoever settled this stage, else whoever holds it now. A stage nobody
          // has reached yet has no assignee — say so rather than borrow a name.
          const resolvedId = decidedBy ?? assignedTo;
          const name = people.find((p) => p.id === resolvedId)?.full_name ?? 'Unassigned';
          const hasOwner = Boolean(resolvedId);
          // When this stage last moved. Four stages stamp their own timestamp, which
          // is exact; the other two fall back to the newest action by the owning role
          // — accurate there because the Copywriter and Designer each own one stage.
          const stampedAt = STAGE_AT[stage] ? (brief[STAGE_AT[stage]!] as string | null) : null;
          const lastAt =
            stampedAt ??
            (events ? [...events].reverse().find((e) => e.actor_role === role)?.at : undefined);

          const sm = STATUS_META[status];
          const Icon = sm.icon;
          const hue = stageHue(s.id);

          return (
            <li
              key={s.id}
              className={cn(
                'flex items-center gap-3 rounded-lg border px-3 py-2.5',
                status === 'active' ? 'border-accent/40 bg-accent-soft' : 'border-separator bg-bg-secondary',
              )}
            >
              {/* Stage identity */}
              <span className="h-8 w-1 rounded-full shrink-0" style={{ background: hue }} aria-hidden />
              <div className="min-w-0 w-32 shrink-0">
                <p className="text-footnote font-semibold text-label truncate">{s.label}</p>
                <p className="text-caption2 text-label-tertiary truncate">{ROLES[role]?.title ?? role}</p>
              </div>

              {/* Assigned person */}
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <span
                  className="grid place-items-center h-6 w-6 rounded-full text-caption2 font-bold text-white shrink-0"
                  style={{ background: hasOwner ? ROLES[role]?.accent ?? '#8e8e93' : 'var(--color-label-tertiary)' }}
                >
                  {hasOwner ? initials(name) : '—'}
                </span>
                <span className={cn('text-footnote truncate', hasOwner ? 'text-label' : 'text-label-tertiary italic')}>
                  {name}
                </span>
              </div>

              {/* When it last moved */}
              {lastAt && <span className="hidden sm:inline text-caption2 text-label-tertiary whitespace-nowrap">{timeAgo(lastAt)}</span>}

              {/* Status */}
              <span
                className="inline-flex items-center gap-1.5 h-6 px-2.5 rounded-full text-caption font-semibold whitespace-nowrap shrink-0"
                style={{ color: sm.hue, backgroundColor: `color-mix(in srgb, ${sm.hue} 14%, transparent)` }}
              >
                <Icon size={12} className={status === 'active' ? 'animate-spin [animation-duration:2.5s]' : ''} />
                {sm.label}
              </span>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
