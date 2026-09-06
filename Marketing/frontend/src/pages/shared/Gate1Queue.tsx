import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldCheck, ChevronRight } from 'lucide-react';
import { Page } from '../../components/layout/Page';
import { ListToolbar } from '../../components/layout/ListToolbar';
import { EmptyState } from '../../components/ui/primitives';
import { Button } from '../../components/ui/Button';
import { DataTable, type Column, type TableGroup } from '../../components/ui/DataTable';
import { TitleCell, OwnerCell, StageDots, stageFill, stageLabel, stageHue } from '../../components/ui/cells';
import { api, ApiError } from '../../lib/api';
import { byOldest } from '../../lib/select';
import type { BriefStage, BriefSummary, Stage } from '../../lib/types';

const titleOf = (b: BriefSummary) => b.project_name || b.product_name || 'Untitled brief';

// The three checkpoints an approver sees, in pipeline order.
const CHECKPOINTS: { stage: BriefStage; label: string }[] = [
  { stage: 'brief_review', label: 'Brief review' },
  { stage: 'creative_review', label: 'Creative review' },
  { stage: 'final_signoff', label: 'Final sign-off' },
];

// Approval queue — the Marketing Lead's brief + creative reviews and the Product
// Lead's final sign-off. Each brief here is at a checkpoint assigned to you and
// awaiting your decision; the decision itself happens on the brief detail page.
export default function Gate1Queue() {
  const nav = useNavigate();
  const [queue, setQueue] = useState<BriefSummary[] | null>(null);
  const [denied, setDenied] = useState(false);
  const [q, setQ] = useState('');

  useEffect(() => {
    api
      .approvalQueue()
      .then((rows) => setQueue(rows))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 403) setDenied(true);
        setQueue([]);
      });
  }, []);

  const columns: Column<BriefSummary>[] = [
    { key: 'brief', header: 'Brief', cell: (b) => <TitleCell title={titleOf(b)} sub={b.product_name && b.product_name !== titleOf(b) ? b.product_name : undefined} /> },
    { key: 'owner', header: 'Owner', width: '180px', cell: (b) => <OwnerCell name={b.owner_name} />, hideBelow: 'lg' },
    { key: 'steps', header: 'Steps', width: '150px', align: 'center', cell: (b) => <StageDots stage={b.stage as Stage} />, hideBelow: 'sm' },
    {
      key: 'checkpoint', header: 'Checkpoint', width: '170px', align: 'center',
      cell: (b) => stageLabel(b.stage as Stage), cellStyle: (b) => stageFill(b.stage as Stage),
    },
    {
      key: 'action', header: '', width: '190px', align: 'right',
      cell: (b) => (
        <Button size="sm" onClick={(e) => { e.stopPropagation(); nav(`/briefs/${b.id}`); }}>
          <ShieldCheck size={14} /> Review &amp; decide <ChevronRight size={14} />
        </Button>
      ),
    },
  ];

  const groups: TableGroup<BriefSummary>[] = useMemo(() => {
    const term = q.trim().toLowerCase();
    const rows = (queue ?? []).filter((b) =>
      !term || titleOf(b).toLowerCase().includes(term) || (b.owner_name ?? '').toLowerCase().includes(term),
    ).sort(byOldest);
    return CHECKPOINTS.map((c) => ({
      id: c.stage,
      label: c.label,
      hue: stageHue(c.stage as Stage),
      rows: rows.filter((b) => b.stage === c.stage),
    })).filter((g) => g.rows.length > 0);
  }, [queue, q]);

  return (
    <Page>
      <ListToolbar
        title="Approvals"
        subtitle="Checkpoints assigned to you and waiting on a decision. Open a brief to approve it or send it back."
        count={queue?.length}
        search={q}
        onSearch={setQ}
        searchPlaceholder="Search briefs…"
      />

      {denied && (
        <p className="mb-4 text-footnote text-label-secondary">
          Sign in as an approver (Marketing Lead or Product Lead) to record decisions.
        </p>
      )}

      {queue === null ? (
        <div className="flex justify-center py-12">
          <span className="h-6 w-6 rounded-full border-2 border-separator border-t-accent animate-spin" aria-label="Loading" />
        </div>
      ) : (
        <DataTable
          columns={columns}
          groups={groups}
          rowKey={(b) => String(b.id)}
          onRowClick={(b) => nav(`/briefs/${b.id}`)}
          empty={
            <EmptyState
              icon={<ShieldCheck size={26} />}
              title={q ? 'No matching briefs' : 'Nothing waiting on you'}
              body={q ? 'Try a different search term.' : 'No briefs need your approval right now.'}
            />
          }
        />
      )}
    </Page>
  );
}
