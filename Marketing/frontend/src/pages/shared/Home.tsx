import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ListTodo, Loader2, CheckCircle2, Layers, Clock, Activity as ActivityIcon,
} from 'lucide-react';
import { useApp } from '../../state/AppContext';
import { ROLES } from '../../lib/roles';
import { Page } from '../../components/layout/Page';
import { Card, Avatar, EmptyState, Skeleton } from '../../components/ui/primitives';
import { Greeting, StatGrid, Stat } from '../../components/feature/HomeKit';
import { BarTrend, HBars, type CategoryDatum } from '../../components/feature/Charts';
import { api } from '../../lib/api';
import { timeAgo } from '../../lib/select';
import { designStatus } from '../../lib/design';
import type { BriefEvent, RoleId, TrendPoint } from '../../lib/types';

// Home is a single dashboard for every role: what's done, what needs doing, a
// 14-day activity graph and the recent activity feed. The KPI + breakdown data
// is role-specific; the graph and feed come from the shared brief audit trail.

interface Kpi { icon: ReactNode; label: string; value: number; accent?: boolean }
interface Dash { kpis: Kpi[]; breakdown: CategoryDatum[]; breakdownTitle: string }

async function buildDash(role: RoleId): Promise<Dash> {
  if (role === 'CW') {
    const q = await api.copywritingQueue().catch(() => []);
    const todo = q.filter((b) => b.creative_count === 0).length;
    const done = q.filter((b) => b.creative_count > 0).length;
    return {
      kpis: [
        { icon: <ListTodo size={18} />, label: 'Waiting to write', value: todo, accent: todo > 0 },
        { icon: <CheckCircle2 size={18} />, label: 'Copies written', value: done },
        { icon: <Layers size={18} />, label: 'In your court', value: q.length },
      ],
      breakdownTitle: 'Copy work',
      breakdown: [
        { label: 'Waiting to write', value: todo },
        { label: 'Copies written', value: done },
      ],
    };
  }

  if (role === 'DS') {
    const q = await api.designQueue().catch(() => []);
    const by = { not_started: 0, in_progress: 0, ready: 0, done: 0 };
    q.forEach((b) => { by[designStatus(b)] += 1; });
    const todo = by.not_started + by.in_progress + by.ready;
    return {
      kpis: [
        { icon: <ListTodo size={18} />, label: 'Needs you', value: todo, accent: todo > 0 },
        { icon: <Loader2 size={18} />, label: 'In progress', value: by.in_progress + by.ready },
        { icon: <CheckCircle2 size={18} />, label: 'Shipped', value: by.done },
        { icon: <Layers size={18} />, label: 'Total assets', value: q.length },
      ],
      breakdownTitle: 'Production breakdown',
      breakdown: [
        { label: 'Not started', value: by.not_started },
        { label: 'In progress', value: by.in_progress },
        { label: 'Ready to export', value: by.ready },
        { label: 'Shipped', value: by.done },
      ],
    };
  }

  if (role === 'ML') {
    const q = await api.approvalQueue().catch(() => []);
    const briefReview = q.filter((b) => b.stage === 'brief_review').length;
    const creativeReview = q.filter((b) => b.stage === 'creative_review').length;
    return {
      kpis: [
        { icon: <ListTodo size={18} />, label: 'Awaiting you', value: q.length, accent: q.length > 0 },
        { icon: <Clock size={18} />, label: 'Brief reviews', value: briefReview },
        { icon: <Clock size={18} />, label: 'Creative reviews', value: creativeReview },
      ],
      breakdownTitle: 'Approvals by checkpoint',
      breakdown: [
        { label: 'Brief review', value: briefReview },
        { label: 'Creative review', value: creativeReview },
      ],
    };
  }

  // PL — authors briefs and gives final sign-off.
  const [briefs, approvals] = await Promise.all([
    api.listBriefs().catch(() => []),
    api.approvalQueue().catch(() => []),
  ]);
  const c = { draft: 0, submitted: 0, approved: 0, changes_requested: 0 };
  briefs.forEach((b) => { c[b.status] += 1; });
  const todo = c.draft + c.changes_requested + approvals.length;
  return {
    kpis: [
      { icon: <ListTodo size={18} />, label: 'Needs you', value: todo, accent: todo > 0 },
      { icon: <Loader2 size={18} />, label: 'In review', value: c.submitted },
      { icon: <CheckCircle2 size={18} />, label: 'Approved', value: c.approved },
      { icon: <Layers size={18} />, label: 'Total briefs', value: briefs.length },
    ],
    breakdownTitle: 'Briefs by status',
    breakdown: [
      { label: 'Drafts', value: c.draft },
      { label: 'Changes requested', value: c.changes_requested },
      { label: 'In review', value: c.submitted },
      { label: 'Approved', value: c.approved },
    ],
  };
}

// 14 daily buckets ending today; each bucket counts the events that landed then.
function toTrend(events: BriefEvent[]): TrendPoint[] {
  const days = 14;
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const buckets: TrendPoint[] = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(start);
    d.setDate(start.getDate() - i);
    buckets.push({ bucket: d.toISOString(), value: 0 });
  }
  const index = new Map(buckets.map((b, i) => [new Date(b.bucket).getTime(), i]));
  events.forEach((e) => {
    const d = new Date(e.at);
    d.setHours(0, 0, 0, 0);
    const i = index.get(d.getTime());
    if (i != null) buckets[i].value += 1;
  });
  return buckets;
}

// ----- Loading skeletons — mirror the real layout so nothing jumps on arrival.
function StatSkeleton() {
  return (
    <Card className="p-4 h-full">
      <Skeleton className="h-5 w-5 rounded-md mb-3" />
      <Skeleton className="h-7 w-16 mb-2" />
      <Skeleton className="h-3 w-24" />
    </Card>
  );
}

function FeedSkeleton() {
  return (
    <ul className="flex flex-col gap-3 pt-1">
      {Array.from({ length: 6 }).map((_, i) => (
        <li key={i} className="flex items-center gap-3">
          <Skeleton className="h-[30px] w-[30px] rounded-full shrink-0" />
          <div className="min-w-0 flex-1">
            <Skeleton className="h-3.5 w-3/4 mb-1.5" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </li>
      ))}
    </ul>
  );
}

function DashSkeleton({ showActivity }: { showActivity: boolean }) {
  return (
    <>
      <StatGrid>
        {Array.from({ length: 4 }).map((_, i) => (
          <StatSkeleton key={i} />
        ))}
      </StatGrid>

      <div className={showActivity ? 'grid lg:grid-cols-3 gap-4 items-start' : 'flex flex-col gap-4'}>
        <div className={showActivity ? 'lg:col-span-2 flex flex-col gap-4' : 'flex flex-col gap-4'}>
          <Card className="p-5">
            <Skeleton className="h-4 w-40 mb-4" />
            <Skeleton className="h-[140px] w-full rounded-lg" />
          </Card>
          <Card className="p-5">
            <Skeleton className="h-4 w-40 mb-4" />
            <div className="flex flex-col gap-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-6 w-full" />
              ))}
            </div>
          </Card>
        </div>

        {showActivity && (
          <Card className="p-5">
            <Skeleton className="h-4 w-32 mb-4" />
            <FeedSkeleton />
          </Card>
        )}
      </div>
    </>
  );
}

export default function Home() {
  const { role, user, bcInbox, cwCopyPending, approvalPending, designPending } = useApp();
  const nav = useNavigate();
  const [events, setEvents] = useState<BriefEvent[] | null>(null);
  const [dash, setDash] = useState<Dash | null>(null);
  const showActivity = role !== 'ML';

  useEffect(() => {
    api.briefAudit().then(setEvents).catch(() => setEvents([]));
  }, []);

  // Re-derive the dashboard whenever the shared queue counts change (e.g. after
  // an approval elsewhere) so the KPI numbers always match the live queues.
  useEffect(() => {
    if (!role) return;
    let alive = true;
    buildDash(role).then((d) => alive && setDash(d));
    return () => { alive = false; };
  }, [role, bcInbox.length, cwCopyPending, approvalPending, designPending]);

  const trend = useMemo(() => toTrend(events ?? []), [events]);
  // Recent activity is a view → newest first.
  const recent = [...(events ?? [])].sort((a, b) => b.at.localeCompare(a.at)).slice(0, 9);
  const name = user?.full_name ?? '';
  const title = role ? ROLES[role].title : '';
  const openEvent = (e: BriefEvent) => nav(role === 'DS' ? `/assets/${e.brief_id}` : `/briefs/${e.brief_id}`);

  return (
    <Page>
      <Greeting name={name} role={title} />

      {!dash ? (
        <DashSkeleton showActivity={showActivity} />
      ) : (
        <>
          <StatGrid>
            {dash.kpis.map((k) => (
              <Stat key={k.label} icon={k.icon} label={k.label} value={k.value} accent={k.accent} />
            ))}
          </StatGrid>

          <div className={showActivity ? 'grid lg:grid-cols-3 gap-4 items-start' : 'flex flex-col gap-4'}>
            {/* Left — the graphs */}
            <div className={showActivity ? 'lg:col-span-2 flex flex-col gap-4' : 'flex flex-col gap-4'}>
              <Card className="p-5">
                <div className="flex items-center gap-2 mb-4">
                  <ActivityIcon size={16} className="text-label-tertiary" />
                  <h2 className="text-subheadline font-bold text-label">Activity — last 14 days</h2>
                </div>
                <BarTrend
                  data={trend}
                  height={140}
                  formatValue={(v) => `${v} update${v === 1 ? '' : 's'}`}
                  emptyLabel="No recent activity"
                />
              </Card>

              <Card className="p-5">
                <h2 className="text-subheadline font-bold text-label mb-4">{dash.breakdownTitle}</h2>
                <HBars data={dash.breakdown} emptyLabel="Nothing here yet" />
              </Card>
            </div>

            {/* Right — recent activity feed (hidden for the Marketing Lead) */}
            {showActivity && (
              <Card className="p-5">
                <h2 className="text-subheadline font-bold text-label mb-3">Recent activity</h2>
                {events === null ? (
                  <FeedSkeleton />
                ) : recent.length === 0 ? (
                  <EmptyState icon={<ActivityIcon size={22} />} title="No activity yet" body="Updates across your briefs will show up here." />
                ) : (
                  <ul className="flex flex-col">
                    {recent.map((e, i) => (
                      <li key={e.id}>
                        <button
                          onClick={() => openEvent(e)}
                          className={`w-full text-left flex gap-3 py-2.5 focus-ring rounded-md ${i > 0 ? 'border-t border-separator' : ''}`}
                        >
                          <Avatar name={e.actor_name} ring={ROLES[e.actor_role as RoleId]?.accent} size={30} />
                          <div className="min-w-0 flex-1">
                            <p className="text-footnote text-label">
                              <span className="font-semibold">{e.actor_name}</span>{' '}
                              <span className="text-label-secondary">{e.action}</span>
                            </p>
                            <p className="text-caption text-label-tertiary truncate">{e.brief_title}</p>
                          </div>
                          <span className="text-caption2 text-label-tertiary shrink-0 whitespace-nowrap">{timeAgo(e.at)}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            )}
          </div>
        </>
      )}
    </Page>
  );
}
