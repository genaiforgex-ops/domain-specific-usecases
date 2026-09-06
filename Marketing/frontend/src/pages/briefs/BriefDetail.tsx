import { useEffect, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Pencil, MessageSquareWarning, AlertCircle, Trash2, ShieldCheck } from 'lucide-react';
import { useApp } from '../../state/AppContext';
import { Page, PageHeader } from '../../components/layout/Page';
import { Card, Pill } from '../../components/ui/primitives';
import { Tabs, type TabDef } from '../../components/layout/ListToolbar';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { BriefStatusPill, SIZE_LABEL } from '../../components/feature/BriefStatusPill';
import { ApprovalPanel, SignoffActions } from '../../components/feature/ApprovalPanel';
import { DesignReviewGallery } from '../../components/feature/DesignReviewGallery';
import { ReassignControl } from '../../components/feature/ReassignControl';
import { RejectControl } from '../../components/feature/RejectControl';
import { CreativePanel } from '../../components/feature/CreativePanel';
import { BriefDocument } from '../../components/feature/BriefDocument';
import { BriefOwnership } from '../../components/feature/BriefOwnership';
import { BriefProgress, BriefTimeline } from '../../components/feature/BriefTransparency';
import { api, ApiError } from '../../lib/api';
import type { Brief, BriefEvent } from '../../lib/types';

type TabId = 'brief' | 'copies' | 'design' | 'approvals' | 'activity';

export default function BriefDetail() {
  const { id } = useParams();
  const { role, user, people, toast, refreshBriefs } = useApp();
  const nav = useNavigate();
  const loc = useLocation();

  const [brief, setBrief] = useState<Brief | null>(null);
  const [events, setEvents] = useState<BriefEvent[] | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [approveOpen, setApproveOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>('brief');

  const load = () =>
    api
      .getBrief(id!)
      .then(setBrief)
      .catch(() => setNotFound(true));

  // The activity timeline + people strip share one fetch; reload whenever the
  // brief object changes (e.g. after an approval action) so they stay current.
  const loadEvents = () => api.briefEvents(id!).then(setEvents).catch(() => setEvents([]));

  useEffect(() => {
    load();
    loadEvents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // When a panel mutates the brief (approval, copy submit), refresh the trail —
  // and the shared queue counts, so sidebar badges and the dashboard stay correct.
  const onBriefChanged = (b: Brief) => {
    setBrief(b);
    loadEvents();
    refreshBriefs();
  };

  if (notFound) {
    return (
      <Page>
        <PageHeader title="Brief not found" subtitle="It may have been removed, or you don't have access." />
        <Button variant="tinted" onClick={() => nav('/briefs')}>Back to My Briefs</Button>
      </Page>
    );
  }
  if (!brief) {
    return (
      <Page>
        <div className="flex justify-center py-20">
          <span className="h-7 w-7 rounded-full border-2 border-separator border-t-accent animate-spin" aria-label="Loading" />
        </div>
      </Page>
    );
  }

  const isOwner = user?.id === brief.creator_id;
  const editable =
    (isOwner && (brief.status === 'draft' || brief.status === 'changes_requested')) ||
    (role === 'ML' && brief.stage === 'brief_review' && brief.marketing_id === user?.id);
  // The Marketing Lead approves (or sends back) the brief right here at brief review
  // — but only the one it was routed to. The API refuses anyone else ("assigned to
  // another approver"), so offering the panel to every ML just produces a 403.
  const canApproveBrief =
    role === 'ML' &&
    brief.stage === 'brief_review' &&
    brief.brief_review_state === 'pending' &&
    brief.marketing_id === user?.id;
  // The Copywriter, while writing, can bounce the brief back to its author when the
  // brief itself needs changes. Surfaced as a top-right action (mirrors reassign).
  const canReturnToAuthor = role === 'CW' && brief.stage === 'copywriting';
  const isApprover = role === 'ML' || role === 'PL';
  // Back returns to wherever the user actually came from — a brief is reachable from
  // several lists (My Briefs, Approvals, Copies, Search, Inbox), so a role-based guess
  // lands on the wrong one. `location.key` is 'default' only for the first entry in the
  // session (deep link, hard refresh), where there's nothing to pop; fall back to the
  // list this role is most likely to want then.
  const fallbackTo = isApprover ? '/approvals' : role === 'CW' ? '/copies' : '/briefs';
  const goBack = () => (loc.key === 'default' ? nav(fallbackTo) : nav(-1));
  const title = brief.project_name || brief.product_name || 'Untitled brief';

  const designReached =
    brief.stage === 'creative_review' ||
    brief.stage === 'final_signoff' ||
    brief.stage === 'completed';

  const tabs: TabDef[] = [
    { id: 'brief', label: 'Brief' },
    { id: 'copies', label: 'Copies' },
    ...(designReached ? [{ id: 'design', label: 'Design' } as TabDef] : []),
    { id: 'approvals', label: 'Approval cycle' },
    { id: 'activity', label: 'Activity' },
  ];
  // A tab may vanish (e.g. design not yet reached) — fall back to the brief.
  const activeTab: TabId = tabs.some((t) => t.id === tab) ? tab : 'brief';

  const discard = async () => {
    if (!brief) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteBrief(brief.id);
      refreshBriefs();
      toast('Brief deleted', 'default');
      nav('/briefs');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not delete the brief.');
      setBusy(false);
    }
  };

  return (
    <Page>
      <button
        onClick={goBack}
        className="inline-flex items-center gap-1.5 text-footnote text-label-secondary hover:text-label mb-3 focus-ring rounded px-1"
      >
        <ArrowLeft size={15} /> Back
      </button>

      <PageHeader
        eyebrow={`${SIZE_LABEL[brief.brief_type]} brief`}
        title={title}
        subtitle={
          brief.product_name
            ? `Product · ${brief.product_name}`
            : 'The full brief, its approvals and everything produced against it.'
        }
        actions={
          <div className="flex items-center gap-2 flex-wrap justify-end">
            <Pill>{SIZE_LABEL[brief.brief_type]}</Pill>
            <BriefStatusPill status={brief.status} />
            {/* Top-right actions — reassign the active task to a same-role peer
                (holder/Admin only), send the brief back (Copywriter), approve it
                (Marketing Lead at brief review), edit, or delete. The approve and
                delete actions open a confirm popup. */}
            <ReassignControl brief={brief} onChanged={onBriefChanged} size="sm" />
            {canReturnToAuthor && (
              <RejectControl
                brief={brief}
                onChanged={onBriefChanged}
                title="Send this brief back"
                description="If the brief needs changes before you can write the copies, send it back to the author with a note."
                placeholder="What does the author need to change in the brief?"
                confirmLabel="Send back to author"
                size="sm"
              />
            )}
            {canApproveBrief && (
              <Button size="sm" onClick={() => setApproveOpen(true)}>
                <ShieldCheck size={15} /> Approve
              </Button>
            )}
            {editable && (
              <Button variant="tinted" size="sm" onClick={() => nav(`/briefs/${brief.id}/edit`)}>
                <Pencil size={15} /> Edit
              </Button>
            )}
            {isOwner && editable && (
              <Button variant="destructive" size="sm" onClick={() => setConfirmDelete(true)}>
                <Trash2 size={15} /> Delete
              </Button>
            )}
          </div>
        }
      />

      {/* Pipeline position stays visible above the tabs for quick context. */}
      <Card className="p-4 mb-5">
        <BriefProgress stage={brief.stage} />
      </Card>

      <Tabs tabs={tabs} active={activeTab} onChange={(id) => setTab(id as TabId)} />

      {/* --- Brief: the document, read like an article --- */}
      {activeTab === 'brief' && (
        <div className="flex flex-col gap-5">
          {brief.review_note && (
            <Card className="p-4 flex items-start gap-2.5">
              <MessageSquareWarning size={18} className="text-warning mt-0.5 shrink-0" />
              <div>
                <p className="text-footnote font-semibold text-label">Reviewer note</p>
                <p className="text-subheadline text-label-secondary whitespace-pre-wrap">{brief.review_note}</p>
              </div>
            </Card>
          )}

          <BriefDocument brief={brief} />
        </div>
      )}

      {/* --- Copies: the copy-writing lane. --- */}
      {activeTab === 'copies' && (
        <div className="flex flex-col gap-5">
          <CreativePanel brief={brief} role={role} onChanged={onBriefChanged} />
        </div>
      )}

      {/* --- Design: banners for review / sign-off --- */}
      {activeTab === 'design' && designReached && (
        <DesignReviewGallery briefId={brief.id} figmaUrl={brief.figma_file_url} />
      )}

      {/* --- Approval cycle --- */}
      {activeTab === 'approvals' && (
        <div>
          <ApprovalPanel brief={brief} role={role} userId={user?.id} onChanged={onBriefChanged} />
        </div>
      )}

      {/* --- Activity: PMO ownership board + timeline — same fixed height, each
          scrolls internally so the full activity history is always reachable. --- */}
      {activeTab === 'activity' && (
        <div className="grid lg:grid-cols-2 gap-4 items-stretch">
          <BriefOwnership brief={brief} events={events} people={people} />
          <BriefTimeline events={events} />
        </div>
      )}

      {canApproveBrief && (
        <Modal
          open={approveOpen}
          onClose={() => setApproveOpen(false)}
          size="sm"
          title={
            <span className="flex items-center gap-2">
              <ShieldCheck size={17} className="text-accent shrink-0" /> Approve this brief
            </span>
          }
        >
          <p className="text-caption text-label-tertiary">
            Approve to move it into copywriting, or send it back with changes.
          </p>
          <SignoffActions
            brief={brief}
            label="Brief review"
            onChanged={(b) => {
              setApproveOpen(false);
              onBriefChanged(b);
            }}
          />
        </Modal>
      )}

      {isOwner && editable && (
        <Modal
          open={confirmDelete}
          onClose={() => {
            if (!busy) {
              setConfirmDelete(false);
              setError(null);
            }
          }}
          size="sm"
          title={
            <span className="flex items-center gap-2">
              <Trash2 size={17} className="text-error shrink-0" /> Delete this brief
            </span>
          }
          footer={
            <div className="flex justify-end gap-2">
              <Button
                variant="plain"
                onClick={() => {
                  setConfirmDelete(false);
                  setError(null);
                }}
                disabled={busy}
              >
                Cancel
              </Button>
              <Button variant="destructive" onClick={discard} disabled={busy}>
                <Trash2 size={16} /> {busy ? 'Deleting…' : 'Confirm delete'}
              </Button>
            </div>
          }
        >
          <p className="text-caption text-label-tertiary">
            Permanently removes the brief and its history. This can't be undone.
          </p>
          {error && (
            <p className="flex items-center gap-1.5 text-footnote text-error mt-3" role="alert">
              <AlertCircle size={14} className="shrink-0" /> {error}
            </p>
          )}
        </Modal>
      )}
    </Page>
  );
}
