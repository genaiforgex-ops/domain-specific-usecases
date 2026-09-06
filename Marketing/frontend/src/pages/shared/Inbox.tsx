import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Clock, Sparkles, ShieldCheck, Palette } from 'lucide-react';
import { useApp } from '../../state/AppContext';
import { ROLES } from '../../lib/roles';
import { Page } from '../../components/layout/Page';
import { ListToolbar } from '../../components/layout/ListToolbar';
import { EmptyState } from '../../components/ui/primitives';
import { DataTable, type Column, type TableGroup } from '../../components/ui/DataTable';
import { TitleCell, StageDots, designFill, designLabel, monoFill } from '../../components/ui/cells';
import { designStatus, designProgress, DESIGN_STATUS } from '../../lib/design';
import { api } from '../../lib/api';
import { byOldest } from '../../lib/select';
import type { DesignQueueItem, Stage } from '../../lib/types';

const ACCENT = 'var(--color-accent)';
const Loading = () => (
  <div className="flex justify-center py-16">
    <span className="h-6 w-6 rounded-full border-2 border-separator border-t-accent animate-spin" aria-label="Loading" />
  </div>
);

const Next = ({ cta }: { cta: string }) => <span className="text-footnote font-semibold text-accent">{cta}</span>;

export default function Inbox() {
  const { role } = useApp();
  const r = ROLES[role!];
  const isApprover = role === 'ML' || role === 'PL';
  return (
    <Page>
      <ListToolbar
        title="Inbox"
        subtitle={`Work lands here the moment it's handed to you. You're signed in as ${r.title}.`}
      />
      {role === 'PL' && <BriefInbox />}
      {role === 'CW' && <DbInbox kind="copy" />}
      {isApprover && <DbInbox kind="approval" />}
      {role === 'DS' && <DesignerInbox />}
    </Page>
  );
}

interface DbItem { id: string; brief_type: string; stage: Stage; title: string; cta: string }

// Copywriter + approver inboxes share a shape: submitted briefs awaiting the
// signed-in user's next move.
function DbInbox({ kind }: { kind: 'copy' | 'approval' }) {
  const nav = useNavigate();
  const [items, setItems] = useState<DbItem[] | null>(null);

  useEffect(() => {
    const p = kind === 'copy'
      ? api.copywritingQueue().then((q) =>
          q.filter((b) => b.creative_count === 0).sort(byOldest).map((b) => ({
            id: b.id, brief_type: b.brief_type, stage: b.stage as Stage,
            title: b.project_name || b.product_name || 'Untitled brief',
            cta: 'Write the copies & submit for approval',
          })))
      : api.approvalQueue().then((q) =>
          q.sort(byOldest).map((b) => ({
            id: b.id, brief_type: b.brief_type, stage: b.stage as Stage,
            title: b.project_name || b.product_name || 'Untitled brief',
            cta: 'Review the copies & sign off',
          })));
    p.then(setItems).catch(() => setItems([]));
  }, [kind]);

  if (items === null) return <Loading />;

  const columns: Column<DbItem>[] = [
    { key: 'brief', header: 'Brief', cell: (b) => <TitleCell title={b.title} /> },
    { key: 'cta', header: 'Next step', cell: (b) => <Next cta={b.cta} /> },
    { key: 'steps', header: 'Steps', width: '150px', align: 'center', cell: (b) => <StageDots stage={b.stage} />, hideBelow: 'sm' },
  ];
  const groups: TableGroup<DbItem>[] = [{ id: 'inbox', label: 'Needs my action now', hue: ACCENT, rows: items }];

  return (
    <DataTable
      columns={columns}
      groups={groups}
      rowKey={(b) => b.id}
      onRowClick={(b) => nav(`/briefs/${b.id}`)}
      empty={
        <EmptyState
          icon={kind === 'copy' ? <Sparkles size={28} /> : <ShieldCheck size={28} />}
          title="You're all caught up"
          body={kind === 'copy'
            ? 'Briefs arrive here the moment a Product Lead submits them.'
            : 'Briefs arrive here once the Copywriter submits the copies for approval.'}
        />
      }
    />
  );
}

// Designer inbox — briefs handed off for production that still need work.
function DesignerInbox() {
  const nav = useNavigate();
  const [queue, setQueue] = useState<DesignQueueItem[] | null>(null);
  useEffect(() => { api.designQueue().then(setQueue).catch(() => setQueue([])); }, []);
  if (queue === null) return <Loading />;

  const titleOf = (b: DesignQueueItem) => b.project_name || b.product_name || 'Untitled brief';
  const active = queue
    .filter((b) => designStatus(b) !== 'done')
    .sort(byOldest);

  const columns: Column<DesignQueueItem>[] = [
    { key: 'brief', header: 'Brief', cell: (b) => <TitleCell title={titleOf(b)} /> },
    { key: 'steps', header: 'Steps', width: '150px', align: 'center', cell: (b) => <StageDots stage={b.stage as Stage} />, hideBelow: 'sm' },
    { key: 'status', header: 'Status', width: '160px', align: 'center', cell: (b) => designLabel(designStatus(b)), cellStyle: (b) => designFill(designStatus(b)) },
    { key: 'progress', header: 'Progress', width: '190px', cell: (b) => <span className="text-footnote text-label-secondary truncate">{designProgress(b)}</span>, hideBelow: 'md' },
    { key: 'cta', header: 'Next step', cell: (b) => <Next cta={DESIGN_STATUS[designStatus(b)].cta} />, hideBelow: 'lg' },
  ];
  const groups: TableGroup<DesignQueueItem>[] = [{ id: 'inbox', label: 'Needs my action now', hue: ACCENT, rows: active }];

  return (
    <DataTable
      columns={columns}
      groups={groups}
      rowKey={(b) => String(b.id)}
      onRowClick={(b) => nav(`/assets/${b.id}`)}
      empty={
        <EmptyState
          icon={<Palette size={28} />}
          title="You're all caught up"
          body="Briefs arrive here the moment a Copywriter hands off the approved copies for banner production."
        />
      }
    />
  );
}

// Product Lead authoring inbox — drafts to finish and briefs sent back for changes.
function BriefInbox() {
  const { bcInbox } = useApp();
  const nav = useNavigate();

  const columns: Column<(typeof bcInbox)[number]>[] = [
    { key: 'brief', header: 'Brief', cell: (i) => <TitleCell title={i.title} sub={i.review_note ? `“${i.review_note}”` : undefined} /> },
    {
      key: 'state', header: 'State', width: '180px', align: 'center',
      cell: (i) => (i.priority === 'high' ? 'Changes requested' : 'To finish'),
      cellStyle: (i) => (i.priority === 'high' ? monoFill(3) : monoFill(0)),
    },
    { key: 'cta', header: 'Next step', cell: (i) => <Next cta={i.cta} />, hideBelow: 'md' },
    { key: 'steps', header: 'Steps', width: '150px', align: 'center', cell: (i) => <StageDots stage={i.stage as Stage} />, hideBelow: 'sm' },
  ];
  const groups: TableGroup<(typeof bcInbox)[number]>[] = [
    { id: 'inbox', label: 'Needs my action now', hue: ACCENT, rows: [...bcInbox].sort(byOldest) },
  ];

  return (
    <DataTable
      columns={columns}
      groups={groups}
      rowKey={(i) => i.id}
      onRowClick={(i) => nav(i.priority === 'high' ? `/briefs/${i.id}/edit` : `/briefs/${i.id}`)}
      empty={
        <EmptyState
          icon={<Clock size={28} />}
          title="You're all caught up"
          body="No briefs are waiting on you. New drafts and anything sent back for changes show up here."
        />
      }
    />
  );
}
