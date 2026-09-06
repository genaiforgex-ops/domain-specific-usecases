import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, ChevronRight } from 'lucide-react';
import { Page } from '../../components/layout/Page';
import { ListToolbar } from '../../components/layout/ListToolbar';
import { EmptyState } from '../../components/ui/primitives';
import { Button } from '../../components/ui/Button';
import { DataTable, type Column, type TableGroup } from '../../components/ui/DataTable';
import { TitleCell, OwnerCell, StageDots, DateCell, monoFill } from '../../components/ui/cells';
import { api, ApiError } from '../../lib/api';
import { byOldest } from '../../lib/select';
import type { GenerationQueueItem, Stage } from '../../lib/types';

const titleOf = (b: GenerationQueueItem) => b.project_name || b.product_name || 'Untitled brief';

// The Copywriter's copy queue. Briefs land here the moment a Product Lead submits
// them — ready for the Copy Agent to draft, the Copywriter to edit, then submit.
export default function CreativeQueue() {
  const nav = useNavigate();
  const [queue, setQueue] = useState<GenerationQueueItem[] | null>(null);
  const [denied, setDenied] = useState(false);
  const [q, setQ] = useState('');

  useEffect(() => {
    api
      .copywritingQueue()
      .then(setQueue)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 403) setDenied(true);
        setQueue([]);
      });
  }, []);

  const columns: Column<GenerationQueueItem>[] = [
    { key: 'brief', header: 'Brief', cell: (b) => <TitleCell title={titleOf(b)} sub={b.product_name && b.product_name !== titleOf(b) ? b.product_name : undefined} /> },
    { key: 'owner', header: 'Owner', width: '180px', cell: (b) => <OwnerCell name={b.owner_name} />, hideBelow: 'lg' },
    { key: 'steps', header: 'Steps', width: '150px', align: 'center', cell: (b) => <StageDots stage={b.stage as Stage} />, hideBelow: 'sm' },
    {
      key: 'copy', header: 'Copy', width: '160px', align: 'center',
      cell: (b) => (b.creative_count > 0 ? `${b.creative_count} written` : 'Awaiting copy'),
      cellStyle: (b) => (b.creative_count > 0 ? monoFill(4) : monoFill(1)),
    },
    { key: 'updated', header: 'Updated', width: '110px', align: 'right', cell: (b) => <DateCell iso={b.updated_at} />, hideBelow: 'md' },
    {
      key: 'action', header: '', width: '150px', align: 'right',
      cell: (b) => (
        <Button
          size="sm"
          variant={b.creative_count > 0 ? 'tinted' : 'filled'}
          onClick={(e) => { e.stopPropagation(); nav(`/briefs/${b.id}`); }}
        >
          <Sparkles size={14} /> {b.creative_count > 0 ? 'Edit' : 'Write'} <ChevronRight size={14} />
        </Button>
      ),
    },
  ];

  const groups: TableGroup<GenerationQueueItem>[] = useMemo(() => {
    const term = q.trim().toLowerCase();
    const rows = (queue ?? []).filter((b) =>
      !term || titleOf(b).toLowerCase().includes(term) || (b.owner_name ?? '').toLowerCase().includes(term),
    ).sort(byOldest);
    return [
      { id: 'pending', label: 'Waiting to write', hue: 'var(--color-warning)', rows: rows.filter((b) => b.creative_count === 0) },
      { id: 'done', label: 'Copies written', hue: 'var(--color-success)', rows: rows.filter((b) => b.creative_count > 0) },
    ].filter((g) => g.rows.length > 0);
  }, [queue, q]);

  return (
    <Page>
      <ListToolbar
        title="Copies"
        subtitle="Briefs waiting on copy — draft with the agent, edit it, then send it for approval."
        count={queue?.length}
        search={q}
        onSearch={setQ}
        searchPlaceholder="Search briefs…"
      />

      {denied && (
        <p className="mb-4 text-footnote text-label-secondary">
          Sign in as the Copywriter account (<span className="font-mono">cw</span>) to pick up copy work.
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
              icon={<Sparkles size={26} />}
              title={q ? 'No matching briefs' : 'Nothing waiting to write'}
              body={q ? 'Try a different search term.' : 'Briefs land here the moment a Product Lead submits them.'}
            />
          }
        />
      )}
    </Page>
  );
}
