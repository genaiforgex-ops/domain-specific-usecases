import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { useToast } from "../app/ToastContext";
import { PageHeader, Card, DataTable, StatCard, Select, Button, EmptyState } from "../components/ui";

interface Summary {
  total_users: number;
  active_users: number;
  documents: number;
  ai_queries: number;
  tokens_in: number;
  tokens_out: number;
  total_tokens: number;
}

interface TokenPoint { date: string; M1: number; M2: number; M3: number; total: number }
interface ActivityPoint { date: string; logins: number }
interface UserRow {
  id: string;
  email: string;
  display_name: string;
  role: string;
  documents: number;
  queries: number;
  tokens: number;
  last_login: string | null;
}
interface AgentRow {
  agent_name: string;
  queries: number;
  tokens_in: number;
  tokens_out: number;
  tokens: number;
}
interface VendorRow {
  vendor_name: string;
  queries: number;
  tokens_in: number;
  tokens_out: number;
  tokens: number;
}

const RANGES = [
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
];

// Minimal dependency-free bar chart. Renders one bar per point, scaled to the max.
function BarChart({ data, label }: { data: { label: string; value: number }[]; label: string }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  if (data.length === 0) {
    return <EmptyState title={`No ${label.toLowerCase()} yet`} description="Data will appear as the platform is used." />;
  }
  return (
    <div className="bar-chart" aria-label={label}>
      {data.map((d, i) => (
        <div className="bar-chart__col" key={`${d.label}-${i}`} title={`${d.label}: ${d.value.toLocaleString()}`}>
          <div className="bar-chart__bar" style={{ height: `${(d.value / max) * 100}%` }} />
          <span className="bar-chart__tick">{d.label.slice(5)}</span>
        </div>
      ))}
    </div>
  );
}

export function MetricsPage() {
  const toast = useToast();
  const [range, setRange] = useState("30");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [tokens, setTokens] = useState<TokenPoint[]>([]);
  const [activity, setActivity] = useState<ActivityPoint[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [vendors, setVendors] = useState<VendorRow[]>([]);

  const load = useCallback(async () => {
    try {
      const q = `?range_days=${range}`;
      const [s, t, a, u, ag, vd] = await Promise.all([
        api.get<Summary>(`/metrics/summary${q}`),
        api.get<{ points: TokenPoint[] }>(`/metrics/token-trend${q}`),
        api.get<{ points: ActivityPoint[] }>(`/metrics/activity${q}`),
        api.get<{ users: UserRow[] }>(`/metrics/users${q}`),
        api.get<{ agents: AgentRow[] }>(`/metrics/agents${q}`),
        api.get<{ vendors: VendorRow[] }>(`/metrics/vendors${q}`),
      ]);
      setSummary(s);
      setTokens(t.points);
      setActivity(a.points);
      setUsers(u.users);
      setAgents(ag.agents);
      setVendors(vd.vendors);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't load metrics");
    }
  }, [range, toast]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <PageHeader
        breadcrumb="Governance"
        title="Metrics Panel"
        subtitle="Platform usage, AI activity, and token consumption. Range is a rolling window ending today."
        action={
          <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "center" }}>
            <Select value={range} onChange={(e) => setRange(e.target.value)} aria-label="Time range">
              {RANGES.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </Select>
            <Button variant="secondary" onClick={load}>Refresh</Button>
          </div>
        }
      />

      <div className="stat-grid">
        <StatCard label="Total Users" value={summary?.total_users ?? 0} accent="blue" />
        <StatCard label="Active Users" value={summary?.active_users ?? 0} hint="Logged in within range" accent="emerald" />
        <StatCard label="Documents" value={summary?.documents ?? 0} accent="amber" />
        <StatCard label="AI Queries" value={summary?.ai_queries ?? 0} accent="blue" />
        <StatCard
          label="Total Tokens"
          value={summary?.total_tokens ?? 0}
          hint={summary ? `In: ${summary.tokens_in.toLocaleString()} · Out: ${summary.tokens_out.toLocaleString()}` : undefined}
          accent="rose"
        />
      </div>

      <div className="metrics-charts">
        <Card>
          <h2 className="card__title">Token Usage Trend</h2>
          <BarChart
            label="Token usage"
            data={tokens.map((p) => ({ label: p.date, value: p.total }))}
          />
        </Card>
        <Card>
          <h2 className="card__title">Login Activity</h2>
          <BarChart
            label="Login activity"
            data={activity.map((p) => ({ label: p.date, value: p.logins }))}
          />
        </Card>
      </div>

      <div style={{ marginBottom: "var(--space-6)" }}>
      <Card>
        <h2 className="card__title">Token Usage by Agent · M1 classification</h2>
        {agents.length === 0 ? (
          <EmptyState
            title="No agent activity yet"
            description="Run an M1 classification to see per-agent token spend. 'Default' is the built-in run."
          />
        ) : (
          <DataTable>
            <thead>
              <tr>
                <th>Agent</th>
                <th style={{ textAlign: "right" }}>Queries</th>
                <th style={{ textAlign: "right" }}>Tokens In</th>
                <th style={{ textAlign: "right" }}>Tokens Out</th>
                <th style={{ textAlign: "right" }}>Total Tokens</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((a) => (
                <tr key={a.agent_name}>
                  <td>{a.agent_name}</td>
                  <td style={{ textAlign: "right" }}>{a.queries.toLocaleString()}</td>
                  <td style={{ textAlign: "right" }}>{a.tokens_in.toLocaleString()}</td>
                  <td style={{ textAlign: "right" }}>{a.tokens_out.toLocaleString()}</td>
                  <td style={{ textAlign: "right" }}><strong>{a.tokens.toLocaleString()}</strong></td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        )}
      </Card>
      </div>

      <div style={{ marginBottom: "var(--space-6)" }}>
      <Card>
        <h2 className="card__title">Token Usage by Vendor · M2 due diligence</h2>
        {vendors.length === 0 ? (
          <EmptyState
            title="No vendor activity yet"
            description="Run an M2 due-diligence report to see per-vendor token spend."
          />
        ) : (
          <DataTable>
            <thead>
              <tr>
                <th>Vendor</th>
                <th style={{ textAlign: "right" }}>Queries</th>
                <th style={{ textAlign: "right" }}>Tokens In</th>
                <th style={{ textAlign: "right" }}>Tokens Out</th>
                <th style={{ textAlign: "right" }}>Total Tokens</th>
              </tr>
            </thead>
            <tbody>
              {vendors.map((v) => (
                <tr key={v.vendor_name}>
                  <td>{v.vendor_name}</td>
                  <td style={{ textAlign: "right" }}>{v.queries.toLocaleString()}</td>
                  <td style={{ textAlign: "right" }}>{v.tokens_in.toLocaleString()}</td>
                  <td style={{ textAlign: "right" }}>{v.tokens_out.toLocaleString()}</td>
                  <td style={{ textAlign: "right" }}><strong>{v.tokens.toLocaleString()}</strong></td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        )}
      </Card>
      </div>

      <Card>
        <h2 className="card__title">Users · usage in range</h2>
        {users.length === 0 ? (
          <EmptyState title="No users" description="Usage will appear here." />
        ) : (
          <DataTable>
            <thead>
              <tr>
                <th>Email</th>
                <th>Name</th>
                <th>Role</th>
                <th style={{ textAlign: "right" }}>Documents</th>
                <th style={{ textAlign: "right" }}>Queries</th>
                <th style={{ textAlign: "right" }}>Tokens</th>
                <th>Last login</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.email}</td>
                  <td>{u.display_name}</td>
                  <td>{u.role}</td>
                  <td style={{ textAlign: "right" }}>{u.documents.toLocaleString()}</td>
                  <td style={{ textAlign: "right" }}>{u.queries.toLocaleString()}</td>
                  <td style={{ textAlign: "right" }}>{u.tokens.toLocaleString()}</td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    {u.last_login ? new Date(u.last_login).toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        )}
      </Card>
    </div>
  );
}
