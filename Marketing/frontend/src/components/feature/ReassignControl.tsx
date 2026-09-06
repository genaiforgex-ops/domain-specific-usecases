import { useState } from 'react';
import { ArrowLeftRight, AlertCircle } from 'lucide-react';
import { Area } from '../ui/primitives';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';
import { AssigneeSelect } from './AssigneeSelect';
import { api, ApiError } from '../../lib/api';
import { useApp } from '../../state/AppContext';
import { ROLES } from '../../lib/roles';
import type { Brief, BriefStage, ReassignSlot, RoleId } from '../../lib/types';

type SlotCtx = { slot: ReassignSlot; role: RoleId };

// The slot that owns a brief at each stage: the assignee column, the role that
// fills it, and — for the current holder — which Brief field carries it.
const STAGE_SLOT: Partial<Record<BriefStage, SlotCtx & { holder: keyof Brief }>> = {
  draft: { slot: 'author', role: 'PL', holder: 'creator_id' },
  brief_review: { slot: 'marketing_brief', role: 'ML', holder: 'marketing_id' },
  copywriting: { slot: 'copywriter', role: 'CW', holder: 'copywriter_id' },
  design: { slot: 'designer', role: 'DS', holder: 'designer_id' },
  creative_review: { slot: 'marketing_creative', role: 'ML', holder: 'marketing_id' },
  final_signoff: { slot: 'product', role: 'PL', holder: 'product_id' },
};

// The slot actionable at a brief's current stage, regardless of who holds it —
// used by an Admin, who can reassign any brief's active-stage task to a peer in
// that role.
export function activeSlot(brief: Brief): SlotCtx | null {
  const s = STAGE_SLOT[brief.stage];
  return s ? { slot: s.slot, role: s.role } : null;
}

// Who currently holds the brief's active-stage task (the assignee id), if any.
export function activeHolderId(brief: Brief): string | null {
  const s = STAGE_SLOT[brief.stage];
  return s ? ((brief[s.holder] as string | null) ?? null) : null;
}

// Which slot the signed-in user holds on this brief right now, if any. Only the
// current holder of the active-stage task may reassign it — the author (Product
// Lead) while it's a draft, the Marketing Lead while reviewing the brief or the
// design, the Copywriter while writing, the Designer while designing, and the
// Product Lead at final sign-off.
export function reassignContext(
  brief: Brief,
  userId: string | null | undefined,
): SlotCtx | null {
  if (!userId) return null;
  const s = STAGE_SLOT[brief.stage];
  return s && activeHolderId(brief) === userId ? { slot: s.slot, role: s.role } : null;
}

type ButtonSize = 'sm' | 'md' | 'lg';

/** Lets the current holder of a brief's active task hand it to another active
 *  teammate in the same role. Renders a top-level button that opens a popup;
 *  renders nothing when the viewer isn't the holder (or Admin). */
export function ReassignControl({
  brief,
  onChanged,
  onReassigned,
  size = 'md',
}: Readonly<{
  brief: Brief;
  onChanged: (b: Brief) => void;
  /** Called after a successful reassign — e.g. to leave a workspace you no longer own. */
  onReassigned?: () => void;
  /** Trigger-button size (defaults to md). */
  size?: ButtonSize;
}>) {
  const { user, toast, refreshBriefs } = useApp();
  const isAdmin = user?.role === 'AD';
  // The holder can reassign their own task; an Admin can reassign whatever task
  // is active on any brief, to any peer in that role.
  const ctx = isAdmin ? activeSlot(brief) : reassignContext(brief, user?.id);

  const [open, setOpen] = useState(false);
  const [assigneeId, setAssigneeId] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!ctx) return null;
  const roleTitle = ROLES[ctx.role].title;
  // Don't offer the person who already holds it (Admin) or yourself (holder).
  const excludeId = isAdmin ? activeHolderId(brief) : user?.id;
  const label = isAdmin ? 'Assign' : 'Reassign';

  const reset = () => {
    setOpen(false);
    setAssigneeId(null);
    setNote('');
    setError(null);
  };

  const submit = async () => {
    if (!assigneeId) {
      setError(`Pick a ${roleTitle} to hand this to.`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await api.reassignBrief(brief.id, assigneeId, ctx.slot, note);
      toast(`Assigned to a ${roleTitle}`, 'success');
      refreshBriefs();
      reset();
      onChanged(updated);
      onReassigned?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not reassign this brief.');
      setBusy(false);
    }
  };

  return (
    <>
      <Button variant="glass" size={size} onClick={() => setOpen(true)}>
        <ArrowLeftRight size={16} /> {label}
      </Button>

      <Modal
        open={open}
        onClose={reset}
        size="sm"
        title={
          <span className="flex items-center gap-2">
            <ArrowLeftRight size={16} className="text-label-secondary" /> {label}
          </span>
        }
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="plain" onClick={reset} disabled={busy}>Cancel</Button>
            <Button onClick={submit} disabled={busy || !assigneeId}>
              <ArrowLeftRight size={16} /> {busy ? 'Saving…' : isAdmin ? 'Confirm assign' : 'Confirm reassign'}
            </Button>
          </div>
        }
      >
        <p className="text-caption text-label-tertiary mb-3">
          {isAdmin
            ? `Assign this brief's ${roleTitle} task to any active ${roleTitle}. They'll pick it up in their queue.`
            : `Hand this over to another ${roleTitle}. They'll pick it up in their queue.`}
        </p>
        <div className="space-y-3">
          <AssigneeSelect
            role={ctx.role}
            value={assigneeId}
            onChange={setAssigneeId}
            exclude={excludeId}
            label={`${isAdmin ? 'Assign' : 'New'} ${roleTitle}`}
            required
          />
          <Area
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Add a note for the trail (optional) — e.g. why you're handing this over."
          />
          {error && (
            <p className="flex items-center gap-1.5 text-footnote text-error" role="alert">
              <AlertCircle size={14} className="shrink-0" /> {error}
            </p>
          )}
        </div>
      </Modal>
    </>
  );
}
