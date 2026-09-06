import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, FileText } from 'lucide-react';
import { Page } from '../../components/layout/Page';
import { ListToolbar, Tabs, type TabDef } from '../../components/layout/ListToolbar';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/primitives';
import { DataTable, type Column, type TableGroup } from '../../components/ui/DataTable';
import {
  TitleCell, OwnerCell, DateCell, StageDots,
  statusFill, statusLabel, stageFill, stageLabel,
} from '../../components/ui/cells';
import { api } from '../../lib/api';
import { byNewest } from '../../lib/select';
import type { BriefSummary, BriefStatus, Stage } from '../../lib/types';

const titleOf = (b: BriefSummary) => b.project_name || b.product_name || 'Untitled brief';

// The status tabs, in attention order. `all` shows everything.
const TABS: { id: BriefStatus | 'all'; label: string; hue?: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'changes_requested', label: 'Changes requested', hue: 'var(--color-error)' },
  { id: 'draft', label: 'Drafts', hue: 'var(--stage-draft)' },
  { id: 'submitted', label: 'In review', hue: 'var(--color-warning)' },
  { id: 'approved', label: 'Approved', hue: 'var(--color-success)' },
];

export default function MyBriefs() {
  const nav = useNavigate();
  const [briefs, setBriefs] = useState<BriefSummary[] | null>(null);
  const [q, setQ] = useState('');
  const [tab, setTab] = useState<BriefStatus | 'all'>('all');

  useEffect(() => {
    api.listBriefs().then(setBriefs).catch(() => setBriefs([]));
  }, []);

  const columns: Column<BriefSummary>[] = [
    {
      key: 'brief', header: 'Brief',
      cell: (b) => (
        <TitleCell
          title={titleOf(b)}
          sub={b.product_name && b.product_name !== titleOf(b) ? b.product_name : undefined}
        />
      ),
    },
    { key: 'owner', header: 'Owner', width: '180px', cell: (b) => <OwnerCell name={b.owner_name} />, hideBelow: 'lg' },
    {
      key: 'stage', header: 'Stage', width: '150px', align: 'center',
      cell: (b) => stageLabel(b.stage as Stage), cellStyle: (b) => stageFill(b.stage as Stage), hideBelow: 'md',
    },
    {
      key: 'steps', header: 'Steps', width: '150px', align: 'center',
      cell: (b) => <StageDots stage={b.stage as Stage} />, hideBelow: 'sm',
    },
    {
      key: 'status', header: 'Status', width: '170px', align: 'center',
      cell: (b) => statusLabel(b.status), cellStyle: (b) => statusFill(b.status),
    },
    { key: 'updated', header: 'Updated', width: '110px', align: 'right', cell: (b) => <DateCell iso={b.updated_at} />, hideBelow: 'md' },
  ];

  // Search first, then compute per-tab counts off the searched set.
  const searched = useMemo(() => {
    const term = q.trim().toLowerCase();
    return (briefs ?? []).filter((b) =>
      !term ||
      titleOf(b).toLowerCase().includes(term) ||
      (b.product_name ?? '').toLowerCase().includes(term) ||
      (b.owner_name ?? '').toLowerCase().includes(term),
    ).sort(byNewest);
  }, [briefs, q]);

  const tabs: TabDef[] = TABS.map((t) => ({
    ...t,
    count: t.id === 'all' ? searched.length : searched.filter((b) => b.status === t.id).length,
  }));

  const rows = tab === 'all' ? searched : searched.filter((b) => b.status === tab);
  const activeHue = TABS.find((t) => t.id === tab)?.hue ?? 'var(--color-accent)';
  const groups: TableGroup<BriefSummary>[] = [{ id: 'briefs', label: '', hue: activeHue, rows }];

  return (
    <Page>
      <ListToolbar
        title="My Briefs"
        subtitle="Every brief you've raised, from draft to shipped. Pick one to see where it's stuck."
        count={briefs?.length}
        search={q}
        onSearch={setQ}
        searchPlaceholder="Search by name, product, owner…"
        actions={<Button onClick={() => nav('/briefs/new')}><Plus size={18} /> New Brief</Button>}
      />

      <Tabs tabs={tabs} active={tab} onChange={(id) => setTab(id as BriefStatus | 'all')} />

      {briefs === null ? (
        <div className="flex justify-center py-12">
          <span className="h-6 w-6 rounded-full border-2 border-separator border-t-accent animate-spin" aria-label="Loading" />
        </div>
      ) : (
        <DataTable
          columns={columns}
          groups={groups}
          hideGroupHeaders
          rowKey={(b) => String(b.id)}
          onRowClick={(b) => nav(`/briefs/${b.id}`)}
          empty={
            <EmptyState
              icon={<FileText size={26} />}
              title={q || tab !== 'all' ? 'No matching briefs' : 'No briefs yet'}
              body={q || tab !== 'all' ? 'Try another tab or search term.' : 'Start your first brief — pick a size and the template guides the rest.'}
            />
          }
        />
      )}
    </Page>
  );
}
