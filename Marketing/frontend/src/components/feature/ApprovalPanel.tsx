import { useState } from 'react';
import { Check, Clock, ShieldCheck, MessageSquareWarning, AlertCircle } from 'lucide-react';
import { Card, Area } from '../ui/primitives';
import { Button } from '../ui/Button';
import { api, ApiError } from '../../lib/api';
import { cn } from '../../lib/cn';
import type { Brief, BriefStage, Gate1LaneState, RoleId } from '../../lib/types';

type CheckpointDef = {
  stage: BriefStage;
  prefix: 'brief_review' | 'creative_review' | 'final_signoff';
  role: RoleId;
  // Which assignee slot holds this checkpoint — the API only accepts the decision
  // from the approver the brief was routed to.
  assignee: 'marketing_id' | 'product_id';
  label: string;
};

// The sequential approval checkpoints, in pipeline order. The Marketing Lead
// holds two (the brief and the design); the Product Lead gives the final
// sign-off. The action is derived from the brief's current stage.
const CHECKPOINTS: CheckpointDef[] = [
  { stage: 'brief_review', prefix: 'brief_review', role: 'ML', assignee: 'marketing_id', label: 'Brief review (Marketing Lead)' },
  { stage: 'creative_review', prefix: 'creative_review', role: 'ML', assignee: 'marketing_id', label: 'Creative review (Marketing Lead)' },
  { stage: 'final_signoff', prefix: 'final_signoff', role: 'PL', assignee: 'product_id', label: 'Final sign-off (Product Lead)' },
];

const STAGE_ORDER: BriefStage[] = [
  'draft', 'brief_review', 'copywriting', 'design', 'creative_review', 'final_signoff', 'completed',
];

export function ApprovalPanel({
  brief,
  role,
  userId,
  onChanged,
}: Readonly<{
  brief: Brief;
  role: RoleId | null;
  /** The signed-in approver — a checkpoint is only actionable by its assignee. */
  userId?: string | null;
  onChanged: (b: Brief) => void;
}>) {
  // Show once the brief has left draft — the checkpoints are meaningful from
  // brief review onward.
  if (brief.stage === 'draft') return null;

  const active = CHECKPOINTS.find((c) => c.stage === brief.stage) ?? null;
  const activeState = active ? (brief[`${active.prefix}_state` as const] as Gate1LaneState) : null;
  // Assignment matters: the API rejects a decision from an approver the brief
  // wasn't routed to, so showing the buttons to a same-role peer only yields a 403.
  const isAssignee = active !== null && brief[active.assignee] === userId;
  const canSignoff =
    active !== null && active.role === role && activeState === 'pending' && isAssignee;
  const complete = brief.stage === 'completed' || brief.status === 'approved';
  const curIdx = STAGE_ORDER.indexOf(brief.stage);

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-2 mb-3">
        <p className="text-subheadline font-bold text-label">Approvals</p>
        <span className="text-caption text-label-tertiary text-right">Sequential · brief → creative → sign-off</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-2">
        {CHECKPOINTS.map((c) => {
          const state = brief[`${c.prefix}_state` as const] as Gate1LaneState;
          const passed = complete || STAGE_ORDER.indexOf(c.stage) < curIdx;
          const isCurrent = c.stage === brief.stage;
          return (
            <LaneCard
              key={c.prefix}
              label={c.label}
              state={state}
              passed={passed}
              isMine={isCurrent && canSignoff}
            />
          );
        })}
      </div>

      {complete && (
        <p className="mt-3 inline-flex items-center gap-1.5 text-footnote text-success font-medium">
          <ShieldCheck size={14} /> Final sign-off complete — this brief is good to go.
        </p>
      )}

      {canSignoff && active && <SignoffActions brief={brief} label={active.label} onChanged={onChanged} />}

      {/* A same-role peer sees why there's nothing to act on — each checkpoint is
          routed to one approver, and only they (or an Admin) can hand it over. */}
      {active !== null && active.role === role && activeState === 'pending' && !isAssignee && (
        <p className="mt-3 text-caption text-label-tertiary">
          This checkpoint is assigned to another {active.role === 'ML' ? 'Marketing Lead' : 'Product Lead'} — they, or an Admin, can reassign it to you.
        </p>
      )}

      {active !== null && active.role === role && activeState === 'approved' && isAssignee && (
        <p className="mt-3 text-caption text-success">You've approved this checkpoint.</p>
      )}
    </Card>
  );
}

function LaneCard({
  label,
  state,
  passed,
  isMine,
}: Readonly<{ label: string; state: Gate1LaneState; passed: boolean; isMine: boolean }>) {
  const done = state === 'approved' || passed;
  const changes = state === 'changes_requested';
  return (
    <div
      className={cn('rounded-md p-3 border', done ? 'border-transparent' : 'border-separator', isMine && 'ring-2 ring-accent')}
      style={{ background: done ? 'color-mix(in srgb, var(--color-success) 12%, transparent)' : 'var(--color-bg)' }}
    >
      <div className="flex items-center gap-2">
        <span
          className="grid place-items-center h-6 w-6 rounded-full shrink-0"
          style={{
            background: done ? 'var(--color-success)' : 'var(--color-fill-quaternary)',
            color: done ? '#fff' : 'var(--color-warning)',
          }}
        >
          {done ? <Check size={13} strokeWidth={3} /> : <Clock size={13} />}
        </span>
        <div className="min-w-0">
          <p className="text-footnote font-semibold text-label truncate">{label}</p>
          <p className="text-caption" style={{ color: done ? 'var(--color-success)' : 'var(--color-warning)' }}>
            {done ? 'Approved' : changes ? 'Changes requested' : isMine ? 'Your approval needed' : 'Awaiting'}
          </p>
        </div>
      </div>
    </div>
  );
}

export function SignoffActions({
  brief,
  label,
  onChanged,
}: Readonly<{
  brief: Brief;
  label: string;
  onChanged: (b: Brief) => void;
}>) {
  const [mode, setMode] = useState<'view' | 'changes'>('view');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const act = async (action: 'approve' | 'request_changes') => {
    if (action === 'request_changes' && !note.trim()) {
      setError('Add a note explaining what needs to change.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onChanged(await api.approvalSignoff(brief.id, action, note.trim() || undefined));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not record your decision.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-4 border-t border-separator pt-4">
      {mode === 'changes' ? (
        <div className="space-y-3">
          <Area
            autoFocus
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="What needs to change before you can approve?"
          />
          <div className="flex justify-end gap-2">
            <Button variant="plain" onClick={() => setMode('view')} disabled={busy}>Cancel</Button>
            <Button variant="destructive" onClick={() => act('request_changes')} disabled={busy}>
              <MessageSquareWarning size={16} /> Send back
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="tinted" onClick={() => setMode('changes')} disabled={busy}>
            <MessageSquareWarning size={16} /> Request changes
          </Button>
          <Button onClick={() => act('approve')} disabled={busy}>
            <ShieldCheck size={16} /> Approve · {label}
          </Button>
        </div>
      )}
      {error && (
        <p className="flex items-center gap-1.5 text-footnote text-error mt-3" role="alert">
          <AlertCircle size={14} className="shrink-0" /> {error}
        </p>
      )}
    </div>
  );
}
