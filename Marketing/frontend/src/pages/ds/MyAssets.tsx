import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Palette, ChevronRight, ExternalLink } from 'lucide-react';
import { Page } from '../../components/layout/Page';
import { ListToolbar } from '../../components/layout/ListToolbar';
import { EmptyState } from '../../components/ui/primitives';
import { Button } from '../../components/ui/Button';
import { DataTable, type Column, type TableGroup } from '../../components/ui/DataTable';
import { TitleCell, OwnerCell, StageDots, designFill, designLabel, designHue } from '../../components/ui/cells';
import { api, ApiError } from '../../lib/api';
import { byOldest } from '../../lib/select';
import { designStatus, designProgress, type DesignStatus } from '../../lib/design';
import type { DesignQueueItem, Stage } from '../../lib/types';

const titleOf = (b: DesignQueueItem) => b.project_name || b.product_name || 'Untitled brief';

// Group the Designer's briefs by where they are in production — closest to done
// first, shipped last — so what's on them now is always at the top.
const GROUPS: { status: DesignStatus; label: string }[] = [
  { status: 'ready', label: 'Ready to export' },
  { status: 'in_progress', label: 'In progress' },
  { status: 'not_started', label: 'Not started' },
  { status: 'done', label: 'Shipped to Figma' },
];

export default function MyAssets() {
  const nav = useNavigate();
  const [queue, setQueue] = useState<DesignQueueItem[] | null>(null);
  const [denied, setDenied] = useState(false);
  const [q, setQ] = useState('');

  useEffect(() => {
    api
      .designQueue()
      .then(setQueue)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 403) setDenied(true);
        setQueue([]);
      });
  }, []);

  const columns: Column<DesignQueueItem>[] = [
    { key: 'brief', header: 'Brief', cell: (b) => <TitleCell title={titleOf(b)} sub={b.product_name && b.product_name !== titleOf(b) ? b.product_name : undefined} /> },
    { key: 'owner', header: 'Owner', width: '180px', cell: (b) => <OwnerCell name={b.owner_name} />, hideBelow: 'lg' },
    { key: 'steps', header: 'Steps', width: '150px', align: 'center', cell: (b) => <StageDots stage={b.stage as Stage} />, hideBelow: 'sm' },
    {
      key: 'status', header: 'Status', width: '160px', align: 'center',
      cell: (b) => designLabel(designStatus(b)), cellStyle: (b) => designFill(designStatus(b)),
    },
    {
      key: 'progress', header: 'Progress', width: '190px',
      cell: (b) => <span className="text-footnote text-label-secondary truncate">{designProgress(b)}</span>,
      hideBelow: 'md',
    },
    {
      key: 'action', header: '', width: '190px', align: 'right',
      cell: (b) => {
        const status = designStatus(b);
        const shipped = status === 'done';
        return (
          <div className="flex justify-end gap-1.5">
            {shipped && b.figma_file_url && (
              <a href={b.figma_file_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="focus-ring rounded-full">
                <Button size="sm" variant="tinted"><ExternalLink size={14} /> Figma</Button>
              </a>
            )}
            <Button size="sm" variant={shipped ? 'plain' : 'filled'} onClick={(e) => { e.stopPropagation(); nav(`/assets/${b.id}`); }}>
              {shipped ? 'View' : 'Open'} <ChevronRight size={14} />
            </Button>
          </div>
        );
      },
    },
  ];

  const groups: TableGroup<DesignQueueItem>[] = useMemo(() => {
    const term = q.trim().toLowerCase();
    const rows = (queue ?? []).filter((b) =>
      !term || titleOf(b).toLowerCase().includes(term) || (b.owner_name ?? '').toLowerCase().includes(term),
    ).sort(byOldest);
    return GROUPS.map((g) => ({
      id: g.status,
      label: g.label,
      hue: designHue(g.status),
      rows: rows.filter((b) => designStatus(b) === g.status),
    })).filter((g) => g.rows.length > 0);
  }, [queue, q]);

  return (
    <Page>
      <ListToolbar
        title="My Assets"
        subtitle="Briefs waiting on artwork, grouped by production stage — closest to done first."
        count={queue?.length}
        search={q}
        onSearch={setQ}
        searchPlaceholder="Search briefs…"
      />

      {denied && (
        <p className="mb-4 text-footnote text-label-secondary">
          Sign in as the Designer account (<span className="font-mono">ds</span>) to pick up handed-off creatives.
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
          onRowClick={(b) => nav(`/assets/${b.id}`)}
          empty={
            <EmptyState
              icon={<Palette size={26} />}
              title={q ? 'No matching assets' : 'No assets assigned'}
              body={q ? 'Try a different search term.' : 'When a Strategist gives creatives to design, the brief shows up here.'}
            />
          }
        />
      )}
    </Page>
  );
}
