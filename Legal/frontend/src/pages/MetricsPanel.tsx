import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Icon } from "@/components/Icons";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { PageHeader } from "@/components/ui/PageHeader";
import { Select } from "@/components/ui/Select";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type {
  DailyCount,
  DailyTokenTrend,
  MetricsDateRange,
  MetricsSummary,
  MetricsUserRow,
  ModuleDailyTrend,
  ModuleUsage,
  UserSegment,
} from "@/types";

const SEGMENT_COLORS: Record<string, string> = {
  power: "#22c55e",
  regular: "#3b82f6",
  occasional: "#eab308",
  inactive: "#ef4444",
};

const MODULE_ICONS: Record<string, keyof typeof Icon> = {
  legal_bot: "Chat",
  contract_review: "ContractReview",
  document_comparison: "Compare",
  legal_research: "Research",
  msa_automation: "Workflow",
  legal_news: "Radar",
  tasks: "Inbox",
};

type DatePreset = "7" | "30" | "90" | "custom";

function utcDateString(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function presetRange(preset: DatePreset): MetricsDateRange {
  if (preset === "custom") return {};
  const days = Number(preset);
  const end = new Date();
  const start = new Date();
  start.setUTCDate(end.getUTCDate() - (days - 1));
  return { start_date: utcDateString(start), end_date: utcDateString(end) };
}

function formatDayLabel(day: string): string {
  const d = new Date(`${day}T00:00:00Z`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

export function MetricsPanelPage() {
  const [preset, setPreset] = useState<DatePreset>("30");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selectedModule, setSelectedModule] = useState<string>("legal_bot");
  const [loading, setLoading] = useState(true);

  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [loginActivity, setLoginActivity] = useState<DailyCount[]>([]);
  const [usageTrend, setUsageTrend] = useState<ModuleDailyTrend[]>([]);
  const [documentsTrend, setDocumentsTrend] = useState<DailyCount[]>([]);
  const [tokenTrend, setTokenTrend] = useState<DailyTokenTrend[]>([]);
  const [segments, setSegments] = useState<UserSegment[]>([]);
  const [moduleUsage, setModuleUsage] = useState<ModuleUsage[]>([]);
  const [users, setUsers] = useState<MetricsUserRow[]>([]);
  const [usersTotal, setUsersTotal] = useState(0);
  const [chatFeedback, setChatFeedback] = useState<{
    up: number;
    down: number;
    commented: number;
    total_rated: number;
    recent: Array<{
      turn_id: number;
      mode?: string | null;
      feedback?: "up" | "down" | null;
      comment?: string | null;
      query?: string;
    }>;
  } | null>(null);
  const pageSize = 20;

  const range = useMemo((): MetricsDateRange => {
    if (preset === "custom") {
      return {
        start_date: customStart || undefined,
        end_date: customEnd || undefined,
      };
    }
    return presetRange(preset);
  }, [preset, customStart, customEnd]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [
        summaryRes,
        loginRes,
        usageRes,
        docsRes,
        tokenRes,
        segmentsRes,
        modulesRes,
        usersRes,
        chatFbRes,
      ] = await Promise.all([
        api.getMetricsSummary(range),
        api.getMetricsLoginActivity(range),
        api.getMetricsUsageTrend(range),
        api.getMetricsDocumentsTrend(range),
        api.getMetricsTokenTrend(range),
        api.getMetricsUserSegments(range),
        api.getMetricsModuleUsage(range),
        api.getMetricsUsers(range, { search: search || undefined, page, page_size: pageSize }),
        api.getMetricsChatFeedback(range).catch(() => null),
      ]);
      setSummary(summaryRes);
      setLoginActivity(loginRes);
      setUsageTrend(usageRes);
      setDocumentsTrend(docsRes);
      setTokenTrend(tokenRes);
      setSegments(segmentsRes);
      setModuleUsage(modulesRes);
      setUsers(usersRes.items);
      setUsersTotal(usersRes.total);
      setChatFeedback(chatFbRes);
    } finally {
      setLoading(false);
    }
  }, [range, search, page]);

  useEffect(() => {
    if (moduleUsage.length > 0 && !moduleUsage.some((m) => m.module === selectedModule)) {
      setSelectedModule(moduleUsage[0].module);
    }
  }, [moduleUsage, selectedModule]);

  useEffect(() => {
    load();
  }, [load]);

  const moduleTrendData = useMemo(() => {
    const byDay = new Map<string, number>();
    for (const row of usageTrend) {
      if (row.module !== selectedModule) continue;
      byDay.set(row.day, row.count);
    }
    return Array.from(byDay.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([day, count]) => ({ day: formatDayLabel(day), count }));
  }, [usageTrend, selectedModule]);

  const documentsChartData = useMemo(
    () => documentsTrend.map((d) => ({ day: formatDayLabel(d.day), count: d.count })),
    [documentsTrend],
  );

  const loginChartData = useMemo(
    () => loginActivity.map((d) => ({ day: formatDayLabel(d.day), count: d.count })),
    [loginActivity],
  );

  const tokenChartData = useMemo(
    () =>
      tokenTrend.map((d) => ({
        day: formatDayLabel(d.day),
        total: d.total_tokens,
        input: d.input_tokens,
        output: d.output_tokens,
      })),
    [tokenTrend],
  );

  const segmentChartData = useMemo(
    () =>
      segments.map((s) => ({
        name: s.label,
        value: s.count,
        segment: s.segment,
        percentage: s.percentage,
        query_range: s.query_range,
      })),
    [segments],
  );

  async function handleDownload() {
    const csv = await api.downloadMetricsUsersCsv(range, search || undefined);
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "metrics-users.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  function clearFilters() {
    setPreset("30");
    setCustomStart("");
    setCustomEnd("");
    setSearch("");
    setPage(1);
  }

  const totalPages = Math.max(1, Math.ceil(usersTotal / pageSize));

  return (
    <div className="space-y-8 pb-10">
      <PageHeader
        title="Metrics Panel"
        subtitle="Usage data covers a full UTC day (00:00 – 23:59). A March 12th report includes 12/03/2025 00:00 UTC to 12/03/2025 23:59 UTC."
      />

      <Card className="p-4">
        <div className="flex flex-wrap items-center gap-3">
          <Select
            value={preset}
            onChange={(e) => setPreset(e.target.value as DatePreset)}
            className="w-40"
          >
            <option value="7">Last 7 Days</option>
            <option value="30">Last 30 Days</option>
            <option value="90">Last 90 Days</option>
            <option value="custom">Custom Range</option>
          </Select>
          {preset === "custom" && (
            <>
              <Input
                type="date"
                value={customStart}
                onChange={(e) => setCustomStart(e.target.value)}
                className="w-40"
              />
              <Input
                type="date"
                value={customEnd}
                onChange={(e) => setCustomEnd(e.target.value)}
                className="w-40"
              />
            </>
          )}
          <button
            type="button"
            onClick={() => load()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-separator/40 px-3 py-2 text-subheadline hover:bg-bg-secondary"
          >
            <Icon.Refresh className="w-4 h-4" />
            Refresh
          </button>
          <button
            type="button"
            onClick={handleDownload}
            className="inline-flex items-center gap-1.5 rounded-lg border border-separator/40 px-3 py-2 text-subheadline hover:bg-bg-secondary"
          >
            <Icon.Documents className="w-4 h-4" />
            Download
          </button>
          <button
            type="button"
            onClick={clearFilters}
            className="text-subheadline text-label-secondary hover:text-label"
          >
            Clear Filters
          </button>
        </div>
      </Card>

      <section className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 md:gap-4">
        <KpiCard label="Total Users" value={summary?.total_users} loading={loading} />
        <KpiCard label="Documents Uploaded" value={summary?.total_documents} loading={loading} />
        <KpiCard label="Queries Asked" value={summary?.total_queries} loading={loading} />
        <KpiCard label="Active Users" value={summary?.active_users} loading={loading} />
        <KpiCard
          label="Total Tokens Used"
          value={summary?.total_tokens}
          loading={loading}
          sub={
            summary
              ? `In: ${summary.input_tokens.toLocaleString()} · Out: ${summary.output_tokens.toLocaleString()}`
              : undefined
          }
        />
      </section>

      {chatFeedback ? (
        <Card className="p-5">
          <h2 className="text-headline text-label mb-2">LawGenie feedback</h2>
          <p className="text-footnote text-label-secondary mb-3">
            Thumbs and comments from chat turns in this date range.
          </p>
          <div className="flex flex-wrap gap-4 text-subheadline mb-3">
            <span>Up: {chatFeedback.up}</span>
            <span>Down: {chatFeedback.down}</span>
            <span>Comments: {chatFeedback.commented}</span>
            <span>Rated: {chatFeedback.total_rated}</span>
          </div>
          {chatFeedback.recent.length > 0 ? (
            <ul className="space-y-2 text-footnote text-label-secondary max-h-48 overflow-auto">
              {chatFeedback.recent.map((r) => (
                <li key={r.turn_id} className="border-b border-separator/40 pb-1">
                  <span className="text-label">{r.feedback ?? "note"}</span>
                  {r.mode ? ` · ${r.mode}` : ""} — {r.query || "(no query)"}
                  {r.comment ? <div className="italic">{r.comment}</div> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-caption text-label-tertiary">No feedback in range.</p>
          )}
        </Card>
      ) : null}

      <Card className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-headline text-label">Login Activity</h2>
          <a href="#users-table" className="text-caption text-accent hover:underline">
            Go To User Table
          </a>
        </div>
        <div className="h-64">
          {loginChartData.length === 0 ? (
            <EmptyChart />
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={loginChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--separator)" opacity={0.4} />
                <XAxis dataKey="day" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Line type="monotone" dataKey="count" stroke="#3b82f6" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </Card>

      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="p-5 lg:col-span-1">
          <h2 className="text-headline text-label mb-4">User Segments</h2>
          <div className="h-56">
            {segmentChartData.length === 0 ? (
              <EmptyChart />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={segmentChartData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={2}
                  >
                    {segmentChartData.map((entry) => (
                      <Cell key={entry.segment} fill={SEGMENT_COLORS[entry.segment] ?? "#94a3b8"} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
          <div className="mt-4 space-y-2">
            {segments.map((s) => (
              <div
                key={s.segment}
                className="flex items-center justify-between rounded-lg border border-separator/30 px-3 py-2"
              >
                <div>
                  <div className="text-subheadline font-medium text-label">{s.label}</div>
                  <div className="text-caption text-label-tertiary">{s.query_range}</div>
                </div>
                <div className="text-right">
                  <div className="text-subheadline font-semibold tabular-nums">{s.percentage}%</div>
                  <div className="text-caption text-label-tertiary">{s.count} users</div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-5 lg:col-span-2">
          <h2 className="text-headline text-label mb-4">Feature Statistics</h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="md:col-span-1 space-y-1">
              {moduleUsage.map((m) => {
                const iconKey = MODULE_ICONS[m.module] ?? "Activity";
                const I = Icon[iconKey];
                const active = m.module === selectedModule;
                return (
                  <button
                    key={m.module}
                    type="button"
                    onClick={() => setSelectedModule(m.module)}
                    className={`w-full flex items-center gap-2 rounded-lg px-3 py-2 text-left text-subheadline transition-colors ${
                      active
                        ? "bg-accent/10 text-accent font-medium"
                        : "text-label-secondary hover:bg-bg-secondary"
                    }`}
                  >
                    <I className="w-4 h-4 shrink-0" />
                    <span className="truncate">{m.label}</span>
                  </button>
                );
              })}
            </div>
            <div className="md:col-span-3 space-y-4">
              <div>
                <h3 className="text-subheadline font-medium text-label mb-2">
                  Usage Trend · Tracks AI actions on the feature
                </h3>
                <div className="h-48">
                  {moduleTrendData.length === 0 ? (
                    <EmptyChart />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={moduleTrendData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--separator)" opacity={0.4} />
                        <XAxis dataKey="day" tick={{ fontSize: 10 }} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 10 }} />
                        <Tooltip />
                        <Line type="monotone" dataKey="count" stroke="#3b82f6" strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>
              <div>
                <h3 className="text-subheadline font-medium text-label mb-2">
                  Documents Uploaded · Daily totals
                </h3>
                <div className="h-40">
                  {documentsChartData.length === 0 ? (
                    <EmptyChart />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={documentsChartData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--separator)" opacity={0.4} />
                        <XAxis dataKey="day" tick={{ fontSize: 10 }} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 10 }} />
                        <Tooltip />
                        <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>
            </div>
          </div>
        </Card>
      </section>

      <Card className="p-5">
        <h2 className="text-headline text-label mb-4">Token Usage Trend</h2>
        <div className="h-56">
          {tokenChartData.length === 0 ? (
            <EmptyChart />
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={tokenChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--separator)" opacity={0.4} />
                <XAxis dataKey="day" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Line type="monotone" dataKey="total" stroke="#8b5cf6" strokeWidth={2} dot={false} name="Total" />
                <Line type="monotone" dataKey="input" stroke="#22c55e" strokeWidth={1.5} dot={false} name="Input" />
                <Line type="monotone" dataKey="output" stroke="#f59e0b" strokeWidth={1.5} dot={false} name="Output" />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </Card>

      <div id="users-table">
      <Card className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <h2 className="text-headline text-label">
            Users Table · Click a user&apos;s email for audit history
          </h2>
          <Input
            placeholder="Search..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="w-56"
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-subheadline">
            <thead>
              <tr className="border-b border-separator/40 text-left text-caption text-label-tertiary">
                <th className="py-2 pr-4 font-medium">Email</th>
                <th className="py-2 pr-4 font-medium">Name</th>
                <th className="py-2 pr-4 font-medium">Role</th>
                <th className="py-2 pr-4 font-medium text-right">Documents</th>
                <th className="py-2 pr-4 font-medium text-right">Queries</th>
                <th className="py-2 pr-4 font-medium text-right">Tokens</th>
                <th className="py-2 font-medium">Last Login</th>
              </tr>
            </thead>
            <tbody>
              {loading && users.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-label-secondary">
                    Loading…
                  </td>
                </tr>
              )}
              {!loading && users.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-label-secondary">
                    No users found.
                  </td>
                </tr>
              )}
              {users.map((u) => (
                <tr key={u.user_id} className="border-b border-separator/20 hover:bg-bg-secondary/50">
                  <td className="py-2.5 pr-4">
                    <Link
                      to={`/audit?user=${u.user_id}`}
                      className="text-accent hover:underline truncate block max-w-[220px]"
                    >
                      {u.email}
                    </Link>
                  </td>
                  <td className="py-2.5 pr-4 text-label">{u.full_name}</td>
                  <td className="py-2.5 pr-4 text-label-secondary">{u.role}</td>
                  <td className="py-2.5 pr-4 text-right tabular-nums">{u.documents}</td>
                  <td className="py-2.5 pr-4 text-right tabular-nums">{u.queries}</td>
                  <td className="py-2.5 pr-4 text-right tabular-nums">{u.total_tokens.toLocaleString()}</td>
                  <td className="py-2.5 text-label-secondary">
                    {u.last_login_at ? formatDate(u.last_login_at) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between mt-4 text-caption text-label-secondary">
          <span>
            Rows per page: {pageSize} · {(page - 1) * pageSize + 1}–
            {Math.min(page * pageSize, usersTotal)} of {usersTotal}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="rounded border border-separator/40 px-2 py-1 disabled:opacity-40"
            >
              ‹
            </button>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="rounded border border-separator/40 px-2 py-1 disabled:opacity-40"
            >
              ›
            </button>
          </div>
        </div>
      </Card>
      </div>
    </div>
  );
}

function KpiCard({
  label,
  value,
  loading,
  sub,
}: {
  label: string;
  value: number | undefined;
  loading: boolean;
  sub?: string;
}) {
  return (
    <div className="rounded-xl bg-bg border border-separator/40 shadow-card p-4">
      <div className="text-caption font-medium text-label-secondary">{label}</div>
      <div className="mt-2 text-title-2 text-label tabular-nums">
        {loading && value === undefined ? (
          <div className="h-8 w-20 rounded bg-bg-secondary animate-shimmer" />
        ) : (
          (value ?? 0).toLocaleString()
        )}
      </div>
      {sub && <div className="mt-1 text-[11px] text-label-tertiary">{sub}</div>}
    </div>
  );
}

function EmptyChart() {
  return (
    <div className="h-full flex items-center justify-center text-subheadline text-label-tertiary">
      No data for this period
    </div>
  );
}
