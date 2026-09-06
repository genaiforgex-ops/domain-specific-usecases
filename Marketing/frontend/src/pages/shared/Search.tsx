import { useMemo, useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Search as SearchIcon } from 'lucide-react';
import { Page } from '../../components/layout/Page';
import { ListToolbar, FilterChip } from '../../components/layout/ListToolbar';
import { EmptyState } from '../../components/ui/primitives';
import { DataTable, type Column, type TableGroup } from '../../components/ui/DataTable';
import {
  TitleCell, OwnerCell, DateCell, StageDots,
  statusFill, statusLabel, stageFill, stageLabel, stageHue,
} from '../../components/ui/cells';
import { api } from '../../lib/api';
import { useApp } from '../../state/AppContext';
import { byNewest } from '../../lib/select';
import type { BriefStage, BriefSummary, Stage } from '../../lib/types';

const titleOf = (b: BriefSummary) => b.project_name || b.product_name || 'Untitled brief';

// Search is scoped by the server: Admin searches every brief in the pipeline,
// everyone else searches only the briefs they've worked on. The server does the
// text match (debounced); the stage filter is applied client-side.
const STAGE_ORDER: BriefStage[] = [
  'draft', 'brief_review', 'copywriting', 'design', 'creative_review', 'final_signoff', 'completed',
];
const STAGE_FILTERS: (BriefStage | 'all')[] = ['all', ...STAGE_ORDER];
const STAGE_LABEL: Record<BriefStage, string> = {
  draft: 'Draft', brief_review: 'Brief review', copywriting: 'Copywriting', design: 'Design',
  creative_review: 'Creative review', final_signoff: 'Sign-off', completed: 'Completed',
};

export default function SearchPage() {
  const { role } = useApp();
  const isAdmin = role === 'AD';
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [q, setQ] = useState(params.get('q') ?? '');
  const [stage, setStage] = useState<BriefStage | 'all'>('all');
  const [briefs, setBriefs] = useState<BriefSummary[]>([]);

  useEffect(() => { setQ(params.get('q') ?? ''); }, [params]);

  useEffect(() => {
    const t = setTimeout(() => {
      api.allBriefs(q).then(setBriefs).catch(() => setBriefs([]));
    }, 220);
    return () => clearTimeout(t);
  }, [q]);

  const results = useMemo(
    () => (stage === 'all' ? [...briefs] : briefs.filter((b) => b.stage === stage)).sort(byNewest),
    [briefs, stage],
  );

  const columns: Column<BriefSummary>[] = [
    { key: 'brief', header: 'Brief', cell: (b) => <TitleCell title={titleOf(b)} sub={b.product_name && b.product_name !== titleOf(b) ? b.product_name : undefined} /> },
    { key: 'owner', header: 'Owner', width: '180px', cell: (b) => <OwnerCell name={b.owner_name} />, hideBelow: 'lg' },
    { key: 'stage', header: 'Stage', width: '150px', align: 'center', cell: (b) => stageLabel(b.stage as Stage), cellStyle: (b) => stageFill(b.stage as Stage), hideBelow: 'md' },
    { key: 'steps', header: 'Steps', width: '150px', align: 'center', cell: (b) => <StageDots stage={b.stage as Stage} />, hideBelow: 'sm' },
    { key: 'status', header: 'Status', width: '170px', align: 'center', cell: (b) => statusLabel(b.status), cellStyle: (b) => statusFill(b.status) },
    { key: 'updated', header: 'Updated', width: '110px', align: 'right', cell: (b) => <DateCell iso={b.updated_at} />, hideBelow: 'md' },
  ];

  const groups: TableGroup<BriefSummary>[] = useMemo(
    () =>
      STAGE_ORDER.map((s) => ({
        id: s,
        label: STAGE_LABEL[s],
        hue: stageHue(s as Stage),
        rows: results.filter((b) => b.stage === s),
      })).filter((g) => g.rows.length > 0),
    [results],
  );

  return (
    <Page>
      <ListToolbar
        title="Search"
        subtitle={
          isAdmin
            ? "Every brief in the pipeline, whatever stage it's at and whoever owns it."
            : "The briefs you've worked on — search by name, product or owner."
        }
        count={results.length}
        search={q}
        onSearch={setQ}
        searchPlaceholder={isAdmin ? 'Search every brief by name, product, owner…' : 'Search your briefs by name, product, owner…'}
      />
      <div className="flex flex-wrap gap-1.5 mb-4">
        {STAGE_FILTERS.map((s) => (
          <FilterChip key={s} active={stage === s} onClick={() => setStage(s)}>
            {s === 'all' ? 'All stages' : STAGE_LABEL[s]}
          </FilterChip>
        ))}
      </div>

      <DataTable
        columns={columns}
        groups={groups}
        rowKey={(b) => String(b.id)}
        onRowClick={(b) => nav(`/briefs/${b.id}`)}
        empty={<EmptyState icon={<SearchIcon size={26} />} title="No matches" body="Try a different term or clear the stage filter." />}
      />
    </Page>
  );
}
