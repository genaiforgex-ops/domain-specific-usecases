import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { IndianRupee, Coins, Activity, Clock, TrendingUp } from 'lucide-react';
import { Page, PageHeader } from '../../components/layout/Page';
import { Card, Pill } from '../../components/ui/primitives';
import { StatGrid, Stat, Loader } from '../../components/feature/HomeKit';
import { MultiLineTrend, HBars } from '../../components/feature/Charts';
import { fmtINR, timeAgo } from '../../lib/select';
import { api } from '../../lib/api';
import type { CostingDetail, OperationTrendPoint } from '../../lib/types';

// Fixed categorical order/colors for the 3 traced operations — validated for
// CVD separation (see the dataviz skill's palette validator) so a colorblind
// reader can still tell them apart via the pill/legend labels.
const OP_META: Record<string, { label: string; hue: string }> = {
  brief_extract: { label: 'Brief extract', hue: 'var(--color-accent)' },
  copy_generation: { label: 'Copy generation', hue: 'var(--op-copy)' },
  banner_image: { label: 'Banner image', hue: 'var(--op-image)' },
};
const OP_ORDER = ['brief_extract', 'copy_generation', 'banner_image'];
const opLabel = (op: string) => OP_META[op]?.label ?? op;
const opHue = (op: string) => OP_META[op]?.hue ?? 'var(--color-label-tertiary)';
const fmtTokens = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));
const inr = (n: number) => `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 4 })}`;

// Long → wide: one row per day, one column per operation, for the stacked chart.
function pivotByOperation(rows: OperationTrendPoint[]): (Record<string, number> & { bucket: string })[] {
  const byBucket = new Map<string, Record<string, number> & { bucket: string }>();
  for (const r of rows) {
    const row = byBucket.get(r.bucket) ?? ({ bucket: r.bucket } as Record<string, number> & { bucket: string });
    row[r.operation] = r.value;
    byBucket.set(r.bucket, row);
  }
  return [...byBucket.values()].sort((a, b) => a.bucket.localeCompare(b.bucket));
}

export default function Costing() {
  const nav = useNavigate();
  const [c, setC] = useState<CostingDetail | null>(null);
  const [denied, setDenied] = useState(false);

  useEffect(() => {
    api.adminCosting().then(setC).catch(() => setDenied(true));
  }, []);

  if (denied) {
    return (
      <Page>
        <PageHeader eyebrow="Admin" title="Costing" subtitle="Sign in as the Admin account (ad) to view costing." />
      </Page>
    );
  }
  if (!c) return <Page><PageHeader eyebrow="Admin" title="Costing" /><Loader /></Page>;

  const opSeries = OP_ORDER.map((key) => ({ key, label: opLabel(key), color: opHue(key) }));
  const opTrendData = pivotByOperation(c.spend_by_operation_trend);

  return (
    <Page>
      <PageHeader eyebrow="Admin" title="Costing" subtitle="Granular AI spend, derived from logged tokens on every model call." />

      <StatGrid>
        <Stat icon={<IndianRupee size={18} />} label="Total spend" value={fmtINR(c.totals.cost_inr)} />
        <Stat icon={<Coins size={18} />} label="Tokens" value={fmtTokens(c.totals.total_tokens)} />
        <Stat icon={<Activity size={18} />} label="Model calls" value={c.totals.calls} />
        <Stat icon={<Clock size={18} />} label="Avg latency" value={`${c.totals.avg_latency_ms}ms`} />
      </StatGrid>

      {/* Spend over time, split by operation — with the today / 7-day / all-time callouts */}
      <Card className="p-5 mb-3">
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 mb-4">
          <p className="text-headline text-label flex items-center gap-2"><TrendingUp size={16} /> Spend over time</p>
          <div className="flex items-center gap-6">
            <WindowInline label="Today" value={fmtINR(c.windows.today_inr)} />
            <WindowInline label="Last 7 days" value={fmtINR(c.windows.week_inr)} />
            <WindowInline label="All time" value={fmtINR(c.windows.total_inr)} accent />
          </div>
        </div>
        <MultiLineTrend
          data={opTrendData}
          series={opSeries}
          height={140}
          formatValue={(v) => fmtINR(v)}
          emptyLabel="No spend traced yet"
        />
      </Card>

      {/* Where the spend goes — chart + detailed table for operation and model */}
      <div className="grid gap-3 mb-3 xl:grid-cols-2">
        <Card className="p-5">
          <p className="text-headline text-label mb-4">By operation</p>
          <HBars
            data={c.by_operation.map((o) => ({ label: opLabel(o.operation), value: o.cost_inr, color: opHue(o.operation) }))}
            formatValue={(v) => inr(v)}
            emptyLabel="No model calls traced yet"
          />
          <div className="mt-5 overflow-x-auto">
            <table className="w-full text-footnote">
              <thead>
                <tr className="text-label-tertiary text-caption uppercase tracking-wide">
                  <Th className="text-left">Operation</Th>
                  <Th>Calls</Th><Th>In tok</Th><Th>Out tok</Th>
                  <Th>In ₹</Th><Th>Out ₹</Th><Th>Latency</Th><Th>Total ₹</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-separator">
                {c.by_operation.length === 0 ? (
                  <tr><td colSpan={8} className="text-label-tertiary py-3">No model calls traced yet.</td></tr>
                ) : c.by_operation.map((o) => (
                  <tr key={o.operation} className="text-label">
                    <td className="py-2.5"><Pill hue={opHue(o.operation)}>{opLabel(o.operation)}</Pill></td>
                    <Td>{o.calls}</Td>
                    <Td>{fmtTokens(o.input_tokens)}</Td>
                    <Td>{fmtTokens(o.output_tokens)}</Td>
                    <Td>{inr(o.input_cost_inr)}</Td>
                    <Td>{inr(o.output_cost_inr)}</Td>
                    <Td>{o.avg_latency_ms}ms</Td>
                    <Td className="font-semibold">{inr(o.cost_inr)}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card className="p-5">
          <p className="text-headline text-label mb-4">By model</p>
          <HBars
            data={c.by_model.map((m) => ({ label: m.model, value: m.cost_inr }))}
            formatValue={(v) => inr(v)}
            emptyLabel="No model calls traced yet"
          />
          <div className="mt-5 overflow-x-auto">
            <table className="w-full text-footnote">
              <thead>
                <tr className="text-label-tertiary text-caption uppercase tracking-wide">
                  <Th className="text-left">Model</Th>
                  <Th>Calls</Th><Th>In tok</Th><Th>Out tok</Th><Th>Cost ₹</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-separator">
                {c.by_model.length === 0 ? (
                  <tr><td colSpan={5} className="text-label-tertiary py-3">—</td></tr>
                ) : c.by_model.map((m) => (
                  <tr key={m.model} className="text-label">
                    <td className="py-2.5 font-mono text-caption">{m.model}</td>
                    <Td>{m.calls}</Td>
                    <Td>{fmtTokens(m.input_tokens)}</Td>
                    <Td>{fmtTokens(m.output_tokens)}</Td>
                    <Td className="font-semibold">{inr(m.cost_inr)}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {/* Top briefs + recent calls, side by side */}
      <div className="grid gap-3 xl:grid-cols-2">
        <Card className="p-5">
          <p className="text-headline text-label mb-4">Top briefs by spend</p>
          {c.by_brief.length === 0 ? (
            <p className="text-footnote text-label-tertiary">No brief-attributed spend yet.</p>
          ) : (
            <div className="flex flex-col gap-2.5">
              {c.by_brief.map((b) => (
                <button
                  key={b.brief_id ?? b.title}
                  onClick={() => b.brief_id && nav(`/briefs/${b.brief_id}`)}
                  className="text-left focus-ring rounded-lg"
                >
                  <div className="flex items-center justify-between gap-3 rounded-lg px-3 py-2.5 hover:bg-[color:var(--color-fill-quaternary)]">
                    <span className="text-subheadline font-semibold text-label truncate">{b.title}</span>
                    <span className="flex items-center gap-3 shrink-0 text-caption text-label-secondary tabular-nums">
                      <span className="hidden sm:inline">{b.calls} calls</span>
                      <span className="hidden sm:inline">{fmtTokens(b.total_tokens)} tok</span>
                      <span className="text-footnote font-semibold text-label">{inr(b.cost_inr)}</span>
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </Card>

        <Card className="p-5">
          <p className="text-headline text-label mb-4">Recent model calls</p>
          {c.recent_calls.length === 0 ? (
            <p className="text-footnote text-label-tertiary">No model calls traced yet — generate copies or banners to see them here.</p>
          ) : (
            <div className="overflow-x-auto">
              <div className="divide-y divide-separator min-w-[480px]">
                {c.recent_calls.map((r) => (
                  <div key={r.id} className="flex items-center gap-3 py-2.5">
                    <Pill hue={opHue(r.operation)}>{opLabel(r.operation)}</Pill>
                    <span className="text-caption text-label-tertiary font-mono truncate hidden md:block">{r.model}</span>
                    <span className="ml-auto text-caption text-label-secondary tabular-nums">{fmtTokens(r.total_tokens)} tok</span>
                    <span className="text-caption text-label-secondary tabular-nums w-16 text-right">{r.latency_ms}ms</span>
                    <span className="text-footnote font-semibold text-label tabular-nums w-20 text-right">{inr(r.cost_inr)}</span>
                    <span className="text-caption2 text-label-tertiary tabular-nums w-14 text-right hidden sm:block">{timeAgo(r.at)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>
    </Page>
  );
}

function WindowInline({ label, value, accent }: Readonly<{ label: string; value: string; accent?: boolean }>) {
  return (
    <div className="text-right">
      <p className="text-caption2 text-label-tertiary uppercase tracking-wide">{label}</p>
      <p className="text-headline font-bold tabular-nums" style={{ color: accent ? 'var(--color-accent)' : 'var(--color-label)' }}>{value}</p>
    </div>
  );
}

function Th({ children, className = '' }: Readonly<{ children?: React.ReactNode; className?: string }>) {
  return <th className={`py-2 px-2 text-right font-semibold ${className}`}>{children}</th>;
}

function Td({ children, className = '' }: Readonly<{ children?: React.ReactNode; className?: string }>) {
  return <td className={`py-2.5 px-2 text-right tabular-nums ${className}`}>{children}</td>;
}
