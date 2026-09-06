import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Layers, CheckCircle2, IndianRupee, Clock, Sparkles, ShieldCheck, Palette,
  TrendingUp, ArrowRight, SlidersHorizontal, ChevronRight,
} from 'lucide-react';
import { Page, PageHeader } from '../../components/layout/Page';
import { Card } from '../../components/ui/primitives';
import { StatGrid, Stat, HomeSection, Loader } from '../../components/feature/HomeKit';
import { LineTrend, StatusBreakdown } from '../../components/feature/Charts';
import { STATUS_HUE } from '../../components/ui/cells';
import { fmtINR } from '../../lib/select';
import { api } from '../../lib/api';
import type { AdminOverview, AdminUser, BriefStage, BriefStatus, OverviewFilters } from '../../lib/types';

const STAGE_META: Record<BriefStage, { label: string; hue: string }> = {
  draft: { label: 'Draft', hue: 'var(--stage-draft)' },
  brief_review: { label: 'Brief review', hue: 'var(--stage-strategy)' },
  copywriting: { label: 'Copywriting', hue: 'var(--stage-review)' },
  design: { label: 'Design', hue: 'var(--stage-design)' },
  creative_review: { label: 'Creative review', hue: 'var(--stage-strategy)' },
  final_signoff: { label: 'Sign-off', hue: 'var(--stage-gate)' },
  completed: { label: 'Completed', hue: 'var(--color-success)' },
};
const STAGE_ORDER: BriefStage[] = [
  'draft', 'brief_review', 'copywriting', 'design', 'creative_review', 'final_signoff', 'completed',
];

const STATUS_LABELS: Record<BriefStatus, string> = {
  draft: 'Draft',
  submitted: 'Submitted',
  approved: 'Approved',
  changes_requested: 'Changes requested',
};
// Unresolved states first, "approved" last — reads like a progress toward done.
const STATUS_ORDER: BriefStatus[] = ['draft', 'submitted', 'changes_requested', 'approved'];

const RANGES: { key: string; label: string; days: number | null }[] = [
  { key: 'today', label: 'Today', days: 0 },
  { key: '7d', label: 'Last 7 days', days: 7 },
  { key: '30d', label: 'Last 30 days', days: 30 },
  { key: '90d', label: 'Last 90 days', days: 90 },
  { key: 'all', label: 'All time', days: null },
];

const fmtTokens = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));

// Start-of-range as an ISO date (undefined = no lower bound / all time).
function startFor(key: string): string | undefined {
  const range = RANGES.find((r) => r.key === key);
  if (!range || range.days === null) return undefined;
  const d = new Date();
  d.setDate(d.getDate() - range.days);
  return d.toISOString().slice(0, 10);
}

const SELECT_CLASS =
  'h-9 px-2.5 pr-7 rounded-md bg-bg-secondary border border-separator text-footnote text-label focus-ring transition-shadow duration-fast';

export default function Dashboard() {
  const nav = useNavigate();
  const [o, setO] = useState<AdminOverview | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [denied, setDenied] = useState(false);

  const [range, setRange] = useState('all');
  const [status, setStatus] = useState('');
  const [product, setProduct] = useState('');
  const [userId, setUserId] = useState('');

  const filters = useMemo<OverviewFilters>(() => {
    const start = startFor(range);
    return {
      ...(start ? { start } : {}),
      ...(status ? { status: status as BriefStatus } : {}),
      ...(product ? { product } : {}),
      ...(userId ? { user_id: userId } : {}),
    };
  }, [range, status, product, userId]);

  useEffect(() => {
    api.adminListUsers().then(setUsers).catch(() => setUsers([]));
  }, []);

  useEffect(() => {
    setO(null);
    api.adminOverview(filters).then(setO).catch(() => setDenied(true));
  }, [filters]);

  // Deep-link into the oversight list, carrying the active dashboard filters.
  const goto = (extra: Record<string, string>) => {
    const sp = new URLSearchParams();
    if (filters.start) sp.set('start', filters.start);
    if (filters.status) sp.set('status', filters.status);
    if (filters.product) sp.set('product', filters.product);
    if (filters.user_id) sp.set('user_id', filters.user_id);
    for (const [k, v] of Object.entries(extra)) sp.set(k, v);
    nav(`/oversight?${sp.toString()}`);
  };

  if (denied) {
    return (
      <Page>
        <PageHeader eyebrow="Admin" title="Dashboard" subtitle="Sign in as the Admin account (ad) to view the oversight dashboard." />
      </Page>
    );
  }

  const filterBar = (
    <FilterBar
      range={range} setRange={setRange}
      status={status} setStatus={setStatus}
      product={product} setProduct={setProduct}
      userId={userId} setUserId={setUserId}
      products={o?.filter_options.products ?? []}
      users={users}
    />
  );

  if (!o) {
    return (
      <Page>
        <PageHeader eyebrow="Admin" title="Dashboard" subtitle="Cross-pipeline oversight — costing, pending work and throughput." />
        {filterBar}
        <Loader />
      </Page>
    );
  }

  const totalBriefs =
    o.totals.draft + o.totals.brief_review + o.totals.copywriting + o.totals.design +
    o.totals.creative_review + o.totals.final_signoff + o.totals.completed;
  const pendingTotal =
    o.pending.brief_review_total + o.pending.awaiting_copy + o.pending.copywriting_total +
    o.pending.design_total + o.pending.creative_review_total + o.pending.final_signoff_total;
  const maxStage = Math.max(
    o.totals.draft, o.totals.brief_review, o.totals.copywriting, o.totals.design,
    o.totals.creative_review, o.totals.final_signoff, o.totals.completed, 1,
  );
  const statusSegments = STATUS_ORDER.map((s) => ({
    key: s, label: STATUS_LABELS[s], value: o.by_status[s], color: STATUS_HUE[s],
  }));

  return (
    <Page>
      <PageHeader eyebrow="Admin" title="Dashboard" subtitle="Cross-pipeline oversight — costing, pending work and throughput." />

      {filterBar}

      <StatGrid>
        <Stat icon={<Layers size={18} />} label="Total briefs" value={totalBriefs} onClick={() => goto({})} />
        <Stat icon={<Clock size={18} />} label="Open work items" value={pendingTotal} accent={pendingTotal > 0} onClick={() => goto({ stage: 'open', sort: 'waiting' })} />
        <Stat icon={<IndianRupee size={18} />} label="Est. AI spend" value={fmtINR(o.costing.estimated_inr)} onClick={() => nav('/costing')} />
        <Stat icon={<CheckCircle2 size={18} />} label="Shipped to Figma" value={o.throughput.exported} onClick={() => goto({ exported: 'true', sort: 'recent' })} />
      </StatGrid>

      {/* Pipeline · AI spend · Throughput · Review status — four peers across the width */}
      <div className="grid gap-3 mb-3 lg:grid-cols-2 xl:grid-cols-4">
        {/* Pipeline funnel — each bar drills into that stage */}
        <Card className="p-5">
          <p className="text-headline text-label mb-4 flex items-center gap-2"><Layers size={16} /> Pipeline</p>
          <div className="flex flex-col gap-3">
            {STAGE_ORDER.map((s) => {
              const n = o.totals[s];
              const meta = STAGE_META[s];
              return (
                <button
                  key={s}
                  onClick={() => goto({ stage: s })}
                  className="flex items-center gap-3 focus-ring rounded-md text-left group"
                >
                  <span className="w-24 shrink-0 text-footnote font-medium text-label-secondary group-hover:text-label">{meta.label}</span>
                  <div className="flex-1 h-6 rounded-md overflow-hidden" style={{ background: 'var(--color-fill-quaternary)' }}>
                    <div
                      className="h-full rounded-md transition-[width] flex items-center justify-end pr-2"
                      style={{ width: `${Math.max((n / maxStage) * 100, n > 0 ? 8 : 0)}%`, background: meta.hue }}
                    >
                      {n > 0 && <span className="text-caption font-bold text-white tabular-nums">{n}</span>}
                    </div>
                  </div>
                  {n === 0 && <span className="text-caption text-label-tertiary tabular-nums w-4">0</span>}
                </button>
              );
            })}
          </div>
        </Card>

        {/* AI spend — line trend */}
        <Card className="p-5 flex flex-col">
          <p className="text-headline text-label mb-1 flex items-center gap-2"><IndianRupee size={16} /> AI spend</p>
          <p className="text-title-1 font-bold text-label tabular-nums">{fmtINR(o.costing.estimated_inr)}</p>
          <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1 text-caption text-label-tertiary tabular-nums">
            <span>{fmtTokens(o.costing.total_tokens)} tokens</span>
            <span>{o.costing.total_calls} calls</span>
          </div>
          <div className="mt-auto pt-4">
            <LineTrend data={o.spend_trend} height={72} formatValue={(v) => fmtINR(v)} emptyLabel="No spend in this range" />
          </div>
          <button
            onClick={() => nav('/costing')}
            className="mt-3 inline-flex items-center gap-1 text-footnote font-semibold text-accent hover:underline focus-ring rounded self-start"
          >
            View cost breakdown <ArrowRight size={14} />
          </button>
        </Card>

        {/* Throughput — line trend */}
        <Card className="p-5 flex flex-col">
          <p className="text-headline text-label mb-3 flex items-center gap-2"><TrendingUp size={16} /> Throughput</p>
          <div className="grid grid-cols-3 gap-3">
            <MiniStat value={o.throughput.exported} label="Shipped" />
            <MiniStat
              value={o.throughput.avg_lead_time_hours == null ? '—' : `${o.throughput.avg_lead_time_hours}h`}
              label="Avg lead time"
            />
            <MiniStat value={o.throughput.change_requests} label="Change requests" warn={o.throughput.change_requests > 0} />
          </div>
          <div className="mt-auto pt-4">
            <LineTrend data={o.throughput_trend} height={72} color="var(--color-success)" emptyLabel="Nothing shipped in this range" />
          </div>
        </Card>

        {/* Brief review status — how the initial review gate is split */}
        <Card className="p-5 flex flex-col">
          <p className="text-headline text-label mb-1 flex items-center gap-2"><ShieldCheck size={16} /> Review status</p>
          <p className="text-title-1 font-bold text-label tabular-nums">{totalBriefs}</p>
          <p className="text-caption text-label-tertiary mt-0.5">briefs, by review state</p>
          <div className="mt-auto pt-4">
            <StatusBreakdown data={statusSegments} emptyLabel="No briefs yet" />
          </div>
        </Card>
      </div>

      {/* Work pending & bottlenecks — four peers across the width */}
      <HomeSection title="Work pending & bottlenecks">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <PendingCard
            icon={<ShieldCheck size={18} />}
            hue="var(--stage-strategy)"
            owner="Brief review"
            primary={o.pending.brief_review_total}
            primaryLabel="awaiting Marketing review"
            sub="Marketing Lead approves the brief"
            onClick={() => goto({ stage: 'brief_review' })}
          />
          <PendingCard
            icon={<Sparkles size={18} />}
            hue="var(--stage-review)"
            owner="Copywriter"
            primary={o.pending.awaiting_copy}
            primaryLabel="awaiting copy"
            sub={`${o.pending.copywriting_total} with the Copywriter`}
            onClick={() => goto({ stage: 'copywriting' })}
          />
          <PendingCard
            icon={<Palette size={18} />}
            hue="var(--stage-design)"
            owner="Designer"
            primary={o.pending.design_total}
            primaryLabel="in production"
            sub={`${o.throughput.exported} shipped to Figma`}
            onClick={() => goto({ stage: 'design' })}
          />
          <PendingCard
            icon={<ShieldCheck size={18} />}
            hue="var(--stage-strategy)"
            owner="Creative review"
            primary={o.pending.creative_review_total}
            primaryLabel="awaiting Marketing approval"
            sub="Marketing Lead approves the design"
            onClick={() => goto({ stage: 'creative_review' })}
          />
          <PendingCard
            icon={<ShieldCheck size={18} />}
            hue="var(--stage-gate)"
            owner="Final sign-off"
            primary={o.pending.final_signoff_total}
            primaryLabel="awaiting Product sign-off"
            sub="Product Lead's final go"
            onClick={() => goto({ stage: 'final_signoff' })}
          />
          {/* Longest waiting — count card into the oldest-first list */}
          <button onClick={() => goto({ stage: 'open', sort: 'waiting' })} className="text-left focus-ring rounded-lg block">
            <Card className="p-4 h-full hover:shadow-elevated transition-shadow duration-base">
              <div className="flex items-center gap-2 mb-2 text-warning"><Clock size={18} />
                <span className="text-footnote font-semibold text-label">Longest waiting</span>
              </div>
              <p className="text-title-1 font-bold tabular-nums" style={{ color: pendingTotal > 0 ? 'var(--color-warning)' : 'var(--color-label)' }}>{pendingTotal}</p>
              <p className="text-caption text-label-secondary mt-0.5">open briefs waiting</p>
              <p className="text-caption2 text-accent mt-2 inline-flex items-center gap-1">View oldest first <ChevronRight size={12} /></p>
            </Card>
          </button>
        </div>
      </HomeSection>
    </Page>
  );
}

function FilterBar({
  range, setRange, status, setStatus, product, setProduct, userId, setUserId, products, users,
}: Readonly<{
  range: string; setRange: (v: string) => void;
  status: string; setStatus: (v: string) => void;
  product: string; setProduct: (v: string) => void;
  userId: string; setUserId: (v: string) => void;
  products: string[];
  users: AdminUser[];
}>) {
  const active = status || product || userId || range !== 'all';
  return (
    <div className="flex flex-wrap items-center gap-2 mb-6">
      <span className="inline-flex items-center gap-1.5 text-caption font-semibold text-label-tertiary mr-1">
        <SlidersHorizontal size={14} /> Filters
      </span>
      <select className={SELECT_CLASS} value={range} onChange={(e) => setRange(e.target.value)} aria-label="Date range">
        {RANGES.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
      </select>
      <select className={SELECT_CLASS} value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
        <option value="">All statuses</option>
        {(Object.keys(STATUS_LABELS) as BriefStatus[]).map((s) => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
      </select>
      <select className={SELECT_CLASS} value={product} onChange={(e) => setProduct(e.target.value)} aria-label="Product">
        <option value="">All products</option>
        {products.map((p) => <option key={p} value={p}>{p}</option>)}
      </select>
      <select className={SELECT_CLASS} value={userId} onChange={(e) => setUserId(e.target.value)} aria-label="User">
        <option value="">All users</option>
        {users.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
      </select>
      {active && (
        <button
          onClick={() => { setRange('all'); setStatus(''); setProduct(''); setUserId(''); }}
          className="text-caption font-medium text-accent hover:underline focus-ring rounded px-1"
        >
          Reset
        </button>
      )}
    </div>
  );
}

function PendingCard({ icon, hue, owner, primary, primaryLabel, sub, onClick }: Readonly<{
  icon: React.ReactNode; hue: string; owner: string; primary: number; primaryLabel: string; sub: string; onClick: () => void;
}>) {
  return (
    <button onClick={onClick} className="text-left focus-ring rounded-lg block">
      <Card className="p-4 h-full hover:shadow-elevated transition-shadow duration-base">
        <div className="flex items-center gap-2 mb-2" style={{ color: hue }}>{icon}
          <span className="text-footnote font-semibold text-label">{owner}</span>
        </div>
        <p className="text-title-1 font-bold tabular-nums" style={{ color: primary > 0 ? hue : 'var(--color-label)' }}>{primary}</p>
        <p className="text-caption text-label-secondary mt-0.5">{primaryLabel}</p>
        <p className="text-caption2 text-label-tertiary mt-2">{sub}</p>
      </Card>
    </button>
  );
}

function MiniStat({ value, label, warn }: Readonly<{ value: string | number; label: string; warn?: boolean }>) {
  return (
    <div>
      <p className="text-title-2 font-bold tabular-nums" style={{ color: warn ? 'var(--color-warning)' : 'var(--color-label)' }}>{value}</p>
      <p className="text-caption2 text-label-tertiary mt-0.5">{label}</p>
    </div>
  );
}
