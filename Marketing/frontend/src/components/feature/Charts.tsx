import { useId } from 'react';
import {
  ResponsiveContainer, BarChart, Bar, AreaChart, Area, LineChart, Line, XAxis, YAxis, Tooltip as RTooltip,
} from 'recharts';
import type { TrendPoint } from '../../lib/types';

// Compact, single-series time-series charts for the Admin dashboard. Each chart
// shows ONE measure over time (magnitude → bars, trend → line), so there is no
// legend and no categorical palette to validate — a single hue, text in ink
// tokens, recessive axes, a hover crosshair/tooltip. Built on Recharts.

interface TrendProps {
  data: TrendPoint[];
  /** CSS color value for the single series. Defaults to the accent token. */
  color?: string;
  height?: number;
  formatValue?: (v: number) => string;
  emptyLabel?: string;
}

const ACCENT = 'var(--color-accent)';
const TRACK = 'var(--color-fill-quaternary)';
const CROSSHAIR = 'var(--color-separator)';

const fmtBucket = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

function Empty({ label, height }: { label: string; height: number }) {
  return (
    <div
      className="grid place-items-center text-caption text-label-tertiary"
      style={{ height }}
    >
      {label}
    </div>
  );
}

function AxisLabels({ data }: { data: { bucket: string }[] }) {
  if (data.length === 0) return null;
  const first = data[0].bucket;
  const last = data[data.length - 1].bucket;
  return (
    <div className="flex justify-between mt-1.5 text-caption2 text-label-tertiary tabular-nums">
      <span>{fmtBucket(first)}</span>
      {data.length > 1 && <span>{fmtBucket(last)}</span>}
    </div>
  );
}

// Values lead (Strong, high-contrast), the date follows as secondary — the reader
// already knows the series from the card title, so the readout is value-first.
function TrendTooltip({
  active, payload, formatValue,
}: {
  active?: boolean;
  payload?: { payload: TrendPoint }[];
  formatValue: (v: number) => string;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="whitespace-nowrap rounded-md glass shadow-elevated px-2 py-1 text-caption2">
      <span className="font-semibold text-label tabular-nums">{formatValue(point.value)}</span>
      <span className="text-label-tertiary"> · {fmtBucket(point.bucket)}</span>
    </div>
  );
}

export interface CategoryDatum {
  label: string;
  value: number;
  /** CSS color for this category's bar; defaults to the accent token. */
  color?: string;
}

/**
 * Horizontal bars for a small, fixed set of categories (spend by operation /
 * model). Identity comes from the row label + its own hue; the value is
 * direct-labeled, so no legend is needed.
 */
export function HBars({
  data,
  formatValue = (v) => String(v),
  emptyLabel = 'No data',
}: Readonly<{
  data: CategoryDatum[];
  formatValue?: (v: number) => string;
  emptyLabel?: string;
}>) {
  if (data.length === 0) return <Empty label={emptyLabel} height={60} />;
  const max = Math.max(...data.map((d) => d.value), 1);

  return (
    <div className="flex flex-col gap-2.5">
      {data.map((d) => {
        const pct = (d.value / max) * 100;
        return (
          <div key={d.label} className="flex items-center gap-3">
            <span className="w-32 shrink-0 truncate text-footnote text-label-secondary" title={d.label}>
              {d.label}
            </span>
            <div className="flex-1 h-5 rounded-md overflow-hidden" style={{ background: 'var(--color-fill-quaternary)' }}>
              <div
                className="h-full rounded-md"
                style={{ width: `${Math.max(pct, d.value > 0 ? 2 : 0)}%`, background: d.color ?? ACCENT }}
              />
            </div>
            <span className="w-24 shrink-0 text-right text-footnote font-semibold text-label tabular-nums">
              {formatValue(d.value)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** Vertical bars anchored to the baseline — for magnitude over time (AI spend). */
export function BarTrend({
  data,
  color = ACCENT,
  height = 96,
  formatValue = (v) => String(v),
  emptyLabel = 'No data in this range',
}: Readonly<TrendProps>) {
  if (data.length === 0) return <Empty label={emptyLabel} height={height} />;

  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} barCategoryGap={2} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <XAxis dataKey="bucket" hide />
          <YAxis hide domain={[0, 'dataMax']} />
          <RTooltip
            cursor={{ fill: TRACK }}
            content={<TrendTooltip formatValue={formatValue} />}
            wrapperStyle={{ outline: 'none' }}
            isAnimationActive={false}
          />
          <Bar dataKey="value" fill={color} radius={[4, 4, 0, 0]} maxBarSize={28} animationDuration={400} />
        </BarChart>
      </ResponsiveContainer>
      <AxisLabels data={data} />
    </div>
  );
}

/** A line + soft area fill — for a trend over time (throughput). */
export function LineTrend({
  data,
  color = ACCENT,
  height = 96,
  formatValue = (v) => String(v),
  emptyLabel = 'No data in this range',
}: Readonly<TrendProps>) {
  const gradientId = useId().replace(/:/g, '');
  if (data.length === 0) return <Empty label={emptyLabel} height={height} />;

  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 4, right: 2, bottom: 0, left: 2 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.22} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="bucket" hide />
          <YAxis hide domain={[0, 'dataMax']} />
          <RTooltip
            cursor={{ stroke: CROSSHAIR, strokeWidth: 1 }}
            content={<TrendTooltip formatValue={formatValue} />}
            wrapperStyle={{ outline: 'none' }}
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            fill={`url(#${gradientId})`}
            dot={{ r: 2.5, fill: color, stroke: 'var(--color-bg)', strokeWidth: 1.5 }}
            activeDot={{ r: 4, fill: color, stroke: 'var(--color-bg)', strokeWidth: 1.5 }}
            animationDuration={400}
          />
        </AreaChart>
      </ResponsiveContainer>
      <AxisLabels data={data} />
    </div>
  );
}

export interface StatusSegment {
  key: string;
  label: string;
  value: number;
  /** CSS color for this segment's fill and legend dot. */
  color: string;
}

/**
 * A single segmented bar showing how a fixed set of statuses splits a whole
 * (e.g. brief review state) — proportion, not magnitude, is the point. Each
 * segment carries its own hue; the legend direct-labels every segment so
 * identity never rides on color alone.
 */
export function StatusBreakdown({
  data,
  emptyLabel = 'No data yet',
}: Readonly<{ data: StatusSegment[]; emptyLabel?: string }>) {
  const total = data.reduce((sum, d) => sum + d.value, 0);
  if (total === 0) return <Empty label={emptyLabel} height={60} />;

  return (
    <div>
      <div className="flex h-3 gap-[2px] rounded-full overflow-hidden" style={{ background: TRACK }}>
        {data.filter((d) => d.value > 0).map((d) => (
          <div
            key={d.key}
            className="h-full"
            style={{ width: `${(d.value / total) * 100}%`, background: d.color }}
            title={`${d.label}: ${d.value}`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-3">
        {data.map((d) => (
          <div key={d.key} className="flex items-center gap-1.5 text-caption">
            <span className="w-2 h-2 rounded-full shrink-0" style={{ background: d.color }} />
            <span className="text-label-secondary">{d.label}</span>
            <span className="font-semibold text-label tabular-nums">{d.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export interface StackedSeries {
  key: string;
  label: string;
  /** CSS color for this series' fill and legend key. */
  color: string;
}

function StackedTooltip({
  active, payload, series, formatValue,
}: {
  active?: boolean;
  payload?: { payload: Record<string, number> & { bucket: string } }[];
  series: StackedSeries[];
  formatValue: (v: number) => string;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="rounded-md glass shadow-elevated px-2.5 py-1.5 text-caption2 min-w-[150px]">
      <p className="text-label-tertiary mb-1">{fmtBucket(row.bucket)}</p>
      <div className="flex flex-col gap-0.5">
        {series.map((s) => (
          <div key={s.key} className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-1.5 text-label-secondary">
              <span className="inline-block w-2 h-0.5 rounded-full shrink-0" style={{ background: s.color }} />
              {s.label}
            </span>
            <span className="font-semibold text-label tabular-nums">{formatValue(row[s.key] ?? 0)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Multiple line series over the same time axis (spend by operation) —
 * magnitude over time, split by identity. A legend direct-labels every
 * series (as a line key, not a box) and the tooltip lists all of them at
 * the hovered bucket, so no reader has to land the pointer on a line.
 */
export function MultiLineTrend({
  data,
  series,
  height = 140,
  formatValue = (v) => String(v),
  emptyLabel = 'No data in this range',
}: Readonly<{
  data: (Record<string, number> & { bucket: string })[];
  series: StackedSeries[];
  height?: number;
  formatValue?: (v: number) => string;
  emptyLabel?: string;
}>) {
  const hasData = data.some((d) => series.some((s) => (d[s.key] ?? 0) > 0));
  if (!hasData) return <Empty label={emptyLabel} height={height} />;

  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 4, right: 2, bottom: 0, left: 2 }}>
          <XAxis dataKey="bucket" hide />
          <YAxis hide domain={[0, 'dataMax']} />
          <RTooltip
            cursor={{ stroke: CROSSHAIR, strokeWidth: 1 }}
            content={<StackedTooltip series={series} formatValue={formatValue} />}
            wrapperStyle={{ outline: 'none' }}
            isAnimationActive={false}
          />
          {series.map((s) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              stroke={s.color}
              strokeWidth={2}
              dot={{ r: 2.5, fill: s.color, stroke: 'var(--color-bg)', strokeWidth: 1.5 }}
              activeDot={{ r: 4, fill: s.color, stroke: 'var(--color-bg)', strokeWidth: 1.5 }}
              animationDuration={400}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <AxisLabels data={data} />
      <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-3">
        {series.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1.5 text-caption text-label-secondary">
            <span className="inline-block w-2.5 h-0.5 rounded-full shrink-0" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}
