import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { FileText, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { Page } from '../../components/layout/Page';
import { ListToolbar } from '../../components/layout/ListToolbar';
import { EmptyState } from '../../components/ui/primitives';
import { Loader } from '../../components/feature/HomeKit';
import { DataTable, type Column, type TableGroup } from '../../components/ui/DataTable';
import { TitleCell, DateCell, StageDots, statusFill, statusLabel } from '../../components/ui/cells';
import { api, ApiError } from '../../lib/api';
import { byNewest } from '../../lib/select';
import type { AdminBriefRow, BriefStage, Stage } from '../../lib/types';

const STAGE_META: Record<BriefStage, { label: string; hue: string }> = {
  draft: { label: 'Draft', hue: 'var(--stage-draft)' },
  brief_review: { label: 'Brief review', hue: 'var(--stage-strategy)' },
  copywriting: { label: 'Copywriting', hue: 'var(--stage-review)' },
  design: { label: 'Design', hue: 'var(--stage-design)' },
  creative_review: { label: 'Creative review', hue: 'var(--stage-strategy)' },
  final_signoff: { label: 'Sign-off', hue: 'var(--stage-gate)' },
  completed: { label: 'Completed', hue: 'var(--color-success)' },
};
const STAGE_ORDER: BriefStage[] = ['draft', 'brief_review', 'copywriting', 'design', 'creative_review', 'final_signoff', 'completed'];

// Human labels for the ?stage= param, including the 'open' sentinel.
const STAGE_TITLES: Record<string, string> = {
  open: 'Open work items', draft: 'Drafts', brief_review: 'Awaiting brief review',
  copywriting: 'In copywriting', design: 'In design', creative_review: 'Awaiting creative review',
  final_signoff: 'Awaiting final sign-off', completed: 'Completed',
};

function WaitingCell({ b }: { b: AdminBriefRow }) {
  if (b.exported) {
    return <span className="inline-flex items-center gap-1 text-footnote font-semibold text-success"><CheckCircle2 size={13} /> Shipped</span>;
  }
  return (
    <span className={`text-footnote font-semibold tabular-nums ${b.waiting_days >= 3 ? 'text-warning' : 'text-label-secondary'}`}>
      {b.waiting_days >= 3 && <AlertTriangle size={12} className="inline mr-1 -mt-0.5" />}
      {b.waiting_days === 0 ? 'today' : `${b.waiting_days}d waiting`}
    </span>
  );
}

// The filtered brief list the Admin dashboard KPI cards / pipeline bars / the
// "longest waiting" card deep-link into. All scoping comes from the query string.
export default function OversightBriefs() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [rows, setRows] = useState<AdminBriefRow[] | null>(null);
  const [denied, setDenied] = useState(false);

  const query = params.toString();
  useEffect(() => {
    setRows(null);
    api
      .adminBriefs(Object.fromEntries(params) as Record<string, string>)
      .then(setRows)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 403) setDenied(true);
        else setRows([]);
      });
  }, [query]); // eslint-disable-line react-hooks/exhaustive-deps

  const stage = params.get('stage');
  const exported = params.get('exported');
  const sort = params.get('sort');
  let title = 'Briefs';
  if (exported === 'true') title = 'Shipped to Figma';
  else if (stage && STAGE_TITLES[stage]) title = STAGE_TITLES[stage];
  else if (sort === 'waiting') title = 'Longest waiting';

  const columns: Column<AdminBriefRow>[] = [
    { key: 'brief', header: 'Brief', cell: (b) => <TitleCell title={b.title} sub={b.product ?? undefined} /> },
    { key: 'steps', header: 'Steps', width: '150px', align: 'center', cell: (b) => <StageDots stage={b.stage as Stage} />, hideBelow: 'sm' },
    { key: 'status', header: 'Status', width: '170px', align: 'center', cell: (b) => statusLabel(b.status), cellStyle: (b) => statusFill(b.status), hideBelow: 'sm' },
    { key: 'waiting', header: 'Waiting', width: '150px', align: 'right', cell: (b) => <WaitingCell b={b} /> },
    { key: 'updated', header: 'Updated', width: '120px', align: 'right', cell: (b) => <DateCell iso={b.updated_at} />, hideBelow: 'md' },
  ];

  const groups: TableGroup<AdminBriefRow>[] = useMemo(() => {
    // Oversight is a view → newest first, except the "Longest waiting" deep-link
    // which keeps its longest-waiting-first ordering.
    const base = [...(rows ?? [])].sort(
      sort === 'waiting' ? (a, b) => b.waiting_days - a.waiting_days : byNewest,
    );
    return STAGE_ORDER.map((s) => ({
      id: s,
      label: STAGE_META[s].label,
      hue: STAGE_META[s].hue,
      rows: base.filter((b) => b.stage === s),
    })).filter((g) => g.rows.length > 0);
  }, [rows, sort]);

  if (denied) {
    return (
      <Page>
        <ListToolbar title={title} />
        <p className="text-footnote text-label-secondary">Sign in as the Admin account (ad) to view this list.</p>
      </Page>
    );
  }

  return (
    <Page>
      <ListToolbar
        title={title}
        subtitle="Briefs matching the filter you came in on. Open one to see its full history."
        count={rows?.length}
      />
      {!rows ? (
        <Loader />
      ) : (
        <DataTable
          columns={columns}
          groups={groups}
          rowKey={(b) => String(b.id)}
          onRowClick={(b) => nav(`/briefs/${b.id}`)}
          empty={<EmptyState icon={<FileText size={24} />} title="No briefs match" body="Try a different filter or date range." />}
        />
      )}
    </Page>
  );
}
