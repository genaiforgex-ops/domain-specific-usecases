import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ScrollText, Lock, ChevronLeft, ChevronRight } from 'lucide-react';
import { fmtDate } from '../../lib/select';
import { ROLES } from '../../lib/roles';
import { Page, PageHeader } from '../../components/layout/Page';
import { Card, Avatar, EmptyState } from '../../components/ui/primitives';
import { Button } from '../../components/ui/Button';
import { api } from '../../lib/api';
import type { BriefEvent } from '../../lib/types';

// Read-only audit visibility — every role sees the immutable, identity-stamped
// brief event trail in its scope, straight from the DB.
export default function Audit() {
  return (
    <Page>
      <PageHeader
        eyebrow="Read-only"
        title="Audit log"
        subtitle="Immutable, identity-stamped record of every state change in your scope."
      />
      <BriefAudit />
    </Page>
  );
}

function AuditFrame({ children, empty }: { children: React.ReactNode; empty: boolean }) {
  return (
    <Card className="p-2 sm:p-4">
      <div className="flex items-center gap-2 px-2 py-2 text-caption text-label-tertiary">
        <Lock size={12} /> Append-only · cannot be edited or deleted
      </div>
      <ol className="relative pl-4">
        <span className="absolute left-[7px] top-2 bottom-2 w-px bg-separator" aria-hidden />
        {children}
      </ol>
      {empty && (
        <EmptyState
          icon={<ScrollText size={24} />}
          title="No activity yet"
          body="State changes in your scope will appear here as they happen."
        />
      )}
    </Card>
  );
}

function Dot({ hue }: { hue: string }) {
  return (
    <span
      className="absolute left-[-1px] top-3.5 h-2.5 w-2.5 rounded-full ring-2"
      // @ts-expect-error css var
      style={{ background: hue, '--tw-ring-color': 'var(--color-bg)' }}
    />
  );
}

// How many entries fill one page of the trail.
const PAGE_SIZE = 20;

function BriefAudit() {
  const nav = useNavigate();
  const [events, setEvents] = useState<BriefEvent[] | null>(null);
  const [page, setPage] = useState(0);

  useEffect(() => {
    api.briefAudit().then(setEvents).catch(() => setEvents([]));
  }, []);

  if (events === null) {
    return (
      <div className="flex justify-center py-16">
        <span className="h-6 w-6 rounded-full border-2 border-separator border-t-accent animate-spin" aria-label="Loading" />
      </div>
    );
  }

  // Audit is a view → newest first.
  const ordered = [...events].sort((a, b) => b.at.localeCompare(a.at));
  const pageCount = Math.max(1, Math.ceil(ordered.length / PAGE_SIZE));
  // Clamp in case the list shrank out from under the current page.
  const current = Math.min(page, pageCount - 1);
  const start = current * PAGE_SIZE;
  const pageEvents = ordered.slice(start, start + PAGE_SIZE);

  return (
    <>
      <AuditFrame empty={ordered.length === 0}>
        {pageEvents.map((e) => (
          <li key={e.id} className="relative pl-6 py-3">
            <Dot hue={ROLES[e.actor_role]?.accent ?? 'var(--color-accent)'} />
            {/* Avatar leads the row: at full window width a justify-between row would
                strand it thousands of pixels from the entry it belongs to. */}
            <div className="flex items-start gap-3">
              <Avatar name={e.actor_name} ring={ROLES[e.actor_role]?.accent} size={24} />
              <div className="min-w-0">
                <p className="text-subheadline text-label">{e.action}</p>
                {e.note && <p className="text-caption text-label-secondary mt-1 whitespace-pre-wrap">“{e.note}”</p>}
                <p className="text-caption text-label-tertiary mt-1">
                  {e.actor_name}
                  {' · '}
                  <button onClick={() => nav(`/briefs/${e.brief_id}`)} className="hover:text-accent focus-ring rounded">
                    {e.brief_title ?? `Brief #${e.brief_id}`}
                  </button>
                  {' · '}{fmtDate(e.at)}
                </p>
              </div>
            </div>
          </li>
        ))}
      </AuditFrame>
      {ordered.length > PAGE_SIZE && (
        <Pager
          page={current}
          pageCount={pageCount}
          total={ordered.length}
          from={start + 1}
          to={start + pageEvents.length}
          onPrev={() => setPage(current - 1)}
          onNext={() => setPage(current + 1)}
        />
      )}
    </>
  );
}

function Pager({
  page,
  pageCount,
  total,
  from,
  to,
  onPrev,
  onNext,
}: {
  page: number;
  pageCount: number;
  total: number;
  from: number;
  to: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  return (
    <div className="flex items-center justify-between mt-3 px-1">
      <p className="text-caption text-label-tertiary tabular-nums">
        {from}–{to} of {total}
      </p>
      <div className="flex items-center gap-2">
        <Button variant="glass" size="sm" onClick={onPrev} disabled={page === 0}>
          <ChevronLeft size={14} /> Prev
        </Button>
        <span className="text-caption text-label-secondary tabular-nums px-1">
          Page {page + 1} of {pageCount}
        </span>
        <Button variant="glass" size="sm" onClick={onNext} disabled={page >= pageCount - 1}>
          Next <ChevronRight size={14} />
        </Button>
      </div>
    </div>
  );
}
