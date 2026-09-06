import { useCallback, useEffect, useMemo, useState } from "react";

import { CATEGORIES, REGULATORS } from "@/components/news/constants";
import { NewsDetailPanel } from "@/components/news/NewsDetailPanel";
import { NewsFilterBar } from "@/components/news/NewsFilterBar";
import { NewsListItem } from "@/components/news/NewsListItem";
import { PageHeader } from "@/components/ui/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Tabs } from "@/components/ui/Tabs";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { hasPermission } from "@/lib/auth";
import { formatDate } from "@/lib/utils";
import type { DiscoverResult, NewsOverview, RegulatoryUpdate, TrackedSource } from "@/types";

type TabId = "feed" | "action" | "regulator" | "sources";

export function LegalNewsPage() {
  const { user } = useAuth();
  const canFull = hasPermission(user, "legal_news_full");
  const [tab, setTab] = useState<TabId>("feed");
  const [overview, setOverview] = useState<NewsOverview | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const loadOverview = useCallback(async () => {
    try {
      setOverview(await api.newsOverview());
    } catch {
      /* non-fatal */
    }
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview, reloadKey]);

  async function refreshNow() {
    setRefreshing(true);
    setBanner(null);
    try {
      const res = await api.refreshNews();
      setBanner(
        `Refreshed ${res.sources.length} source(s): ${res.total_new} new update(s), ${res.action_required} action-required.`,
      );
      setReloadKey((k) => k + 1);
    } catch (err) {
      setBanner((err as Error).message);
    } finally {
      setRefreshing(false);
    }
  }

  const tabs = [
    { id: "feed", label: "Feed" },
    { id: "action", label: "Action Required", count: overview?.action_required },
    { id: "regulator", label: "By Regulator" },
    { id: "sources", label: "Sources & Discover" },
  ];

  return (
    <div className="space-y-5 pb-10">
      <PageHeader
        title="Regulatory Intelligence"
        subtitle="Track RBI, SEBI, IRDAI, ASCI & more — auto-fetched, web-searched, and AI-summarized."
        actions={
          canFull ? (
            <Button onClick={() => void refreshNow()} disabled={refreshing}>
              {refreshing ? "Refreshing…" : "↻ Refresh now"}
            </Button>
          ) : undefined
        }
      />

      <NewsMetricsStrip overview={overview} />

      {banner && (
        <div className="rounded-lg border border-separator/40 bg-bg-secondary px-4 py-3 text-sm text-label-secondary">
          {banner}
        </div>
      )}

      <Tabs tabs={tabs} active={tab} onChange={(id) => setTab(id as TabId)} />

      {tab === "feed" && (
        <FeedTab canFull={canFull} reloadKey={reloadKey} onChanged={() => setReloadKey((k) => k + 1)} />
      )}
      {tab === "action" && (
        <FeedTab
          canFull={canFull}
          reloadKey={reloadKey}
          fixedStatus="action_required"
          onChanged={() => setReloadKey((k) => k + 1)}
        />
      )}
      {tab === "regulator" && (
        <ByRegulatorTab canFull={canFull} reloadKey={reloadKey} onChanged={() => setReloadKey((k) => k + 1)} />
      )}
      {tab === "sources" && canFull && <SourcesTab onChanged={() => setReloadKey((k) => k + 1)} />}
      {tab === "sources" && !canFull && (
        <Card>
          <div className="text-sm text-label-secondary">You need full Legal News access to manage sources.</div>
        </Card>
      )}
    </div>
  );
}

function NewsMetricsStrip({ overview }: { overview: NewsOverview | null }) {
  const items = [
    { label: "New this week", value: overview?.new_this_week ?? "—", accent: false },
    { label: "Action required", value: overview?.action_required ?? "—", accent: true },
    { label: "Sources tracked", value: overview?.sources_count ?? "—", accent: false },
    {
      label: "Last refreshed",
      value: overview?.last_refreshed ? formatDate(overview.last_refreshed) : "—",
      accent: false,
      isText: true,
    },
  ];

  return (
    <div className="rounded-lg border border-separator/40 bg-bg px-4 py-3 shadow-card">
      <div className="grid grid-cols-2 sm:flex sm:flex-wrap sm:items-center gap-x-4 gap-y-2 sm:divide-x sm:divide-separator/40">
        {items.map((item) => (
          <div key={item.label} className="flex items-baseline gap-2 sm:px-4 sm:first:pl-0 sm:last:pr-0">
            <span className="text-xs uppercase tracking-wider text-label-tertiary whitespace-nowrap">
              {item.label}
            </span>
            <span
              className={`font-semibold tabular-nums ${item.accent ? "text-accent" : "text-label"} ${item.isText ? "text-xs font-medium" : "text-sm"}`}
            >
              {item.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function NewsFeedLayout({
  children,
  selected,
  canFull,
  onClose,
  onChanged,
}: {
  children: React.ReactNode;
  selected: RegulatoryUpdate | null;
  canFull: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  return (
    <div className="relative min-h-[60vh]">
      <div className="space-y-3">{children}</div>
      {selected && (
        <NewsDetailPanel item={selected} canFull={canFull} onClose={onClose} onChanged={onChanged} />
      )}
    </div>
  );
}

function FeedTab({
  canFull,
  reloadKey,
  fixedStatus,
  onChanged,
}: {
  canFull: boolean;
  reloadKey: number;
  fixedStatus?: string;
  onChanged: () => void;
}) {
  const [rows, setRows] = useState<RegulatoryUpdate[]>([]);
  const [filters, setFilters] = useState({ regulator: "", category: "", status: "", q: "" });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(
        await api.listNews({
          regulator: filters.regulator || undefined,
          category: filters.category || undefined,
          status: fixedStatus || filters.status || undefined,
          q: filters.q || undefined,
        }),
      );
    } finally {
      setLoading(false);
    }
  }, [filters, fixedStatus]);

  useEffect(() => {
    void load();
  }, [load, reloadKey]);

  useEffect(() => {
    if (selectedId && !rows.some((r) => r.id === selectedId)) {
      setSelectedId(null);
    }
  }, [rows, selectedId]);

  const selected = rows.find((r) => r.id === selectedId) ?? null;

  return (
    <NewsFeedLayout
      selected={selected}
      canFull={canFull}
      onClose={() => setSelectedId(null)}
      onChanged={onChanged}
    >
      {!fixedStatus && (
        <NewsFilterBar filters={filters} onChange={setFilters} showStatus />
      )}
      {loading ? (
        <Card>
          <div className="text-sm text-label-secondary">Loading…</div>
        </Card>
      ) : rows.length === 0 ? (
        <Card>
          <div className="text-sm text-label-secondary">
            No updates match. Try “Refresh now” or add a source under Sources & Discover.
          </div>
        </Card>
      ) : (
        <div className="space-y-2">
          {rows.map((r) => (
            <NewsListItem
              key={r.id}
              item={r}
              selected={r.id === selectedId}
              onSelect={setSelectedId}
            />
          ))}
        </div>
      )}
    </NewsFeedLayout>
  );
}

function ByRegulatorTab({
  canFull,
  reloadKey,
  onChanged,
}: {
  canFull: boolean;
  reloadKey: number;
  onChanged: () => void;
}) {
  const [rows, setRows] = useState<RegulatoryUpdate[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    void api.listNews({}).then((data) => {
      setRows(data);
      setLoading(false);
    });
  }, [reloadKey]);

  const grouped = useMemo(() => {
    const g: Record<string, RegulatoryUpdate[]> = {};
    for (const r of rows) (g[r.source] ??= []).push(r);
    return Object.entries(g).sort((a, b) => b[1].length - a[1].length);
  }, [rows]);

  useEffect(() => {
    if (selectedId && !rows.some((r) => r.id === selectedId)) {
      setSelectedId(null);
    }
  }, [rows, selectedId]);

  const selected = rows.find((r) => r.id === selectedId) ?? null;

  if (loading) {
    return (
      <Card>
        <div className="text-sm text-label-secondary">Loading…</div>
      </Card>
    );
  }

  if (grouped.length === 0) {
    return (
      <Card>
        <div className="text-sm text-label-secondary">No updates yet.</div>
      </Card>
    );
  }

  return (
    <NewsFeedLayout
      selected={selected}
      canFull={canFull}
      onClose={() => setSelectedId(null)}
      onChanged={onChanged}
    >
      <div className="space-y-6">
        {grouped.map(([regulator, items]) => (
          <div key={regulator} className="space-y-2">
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold text-label">{regulator}</h2>
              <Badge className="bg-bg-secondary text-label-secondary border-separator/40">
                {items.length}
              </Badge>
            </div>
            {items.slice(0, 8).map((r) => (
              <NewsListItem
                key={r.id}
                item={r}
                selected={r.id === selectedId}
                onSelect={setSelectedId}
              />
            ))}
          </div>
        ))}
      </div>
    </NewsFeedLayout>
  );
}

function SourcesTab({ onChanged }: { onChanged: () => void }) {
  const [sources, setSources] = useState<TrackedSource[]>([]);
  const [busyId, setBusyId] = useState<number | "new" | null>(null);
  const [form, setForm] = useState({ name: "", url: "", regulator: "RBI", category: "Banking" });
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    setSources(await api.listSources());
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function addSource(e: React.FormEvent) {
    e.preventDefault();
    setBusyId("new");
    setError(null);
    try {
      await api.createSource({ ...form, source_type: "web" });
      setForm({ name: "", url: "", regulator: "RBI", category: "Banking" });
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  async function toggle(s: TrackedSource) {
    await api.updateSource(s.id, { enabled: !s.enabled });
    await load();
  }

  async function refreshOne(s: TrackedSource) {
    setBusyId(s.id);
    setNote(null);
    try {
      const res = await api.refreshSource(s.id);
      setNote(`${s.name}: ${res.total_new} new update(s).`);
      await load();
      onChanged();
    } catch (err) {
      setNote((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  async function remove(s: TrackedSource) {
    if (!window.confirm(`Stop tracking ${s.name}?`)) return;
    await api.deleteSource(s.id);
    await load();
  }

  return (
    <div className="space-y-5">
      <Card title="Add a source" subtitle="A regulator website or RSS feed to track.">
        <form className="grid sm:grid-cols-2 gap-3" onSubmit={addSource}>
          <Input label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          <Input label="URL" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} required placeholder="https://…" />
          <Select label="Regulator" value={form.regulator} onChange={(e) => setForm({ ...form, regulator: e.target.value })}>
            {REGULATORS.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </Select>
          <Select label="Category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            {CATEGORIES.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </Select>
          {error && <p className="text-sm text-error sm:col-span-2">{error}</p>}
          <div className="sm:col-span-2 flex justify-end">
            <Button type="submit" disabled={busyId === "new"}>
              {busyId === "new" ? "Adding…" : "Add source"}
            </Button>
          </div>
        </form>
      </Card>

      {note && <div className="text-sm text-label-secondary">{note}</div>}

      <Card title="Tracked sources">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-label-secondary border-b border-separator/30">
              <tr>
                <th className="py-2">Name</th>
                <th className="py-2">Regulator</th>
                <th className="py-2">Category</th>
                <th className="py-2">Last fetched</th>
                <th className="py-2">Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.id} className="border-b border-separator/20">
                  <td className="py-2">
                    <a href={s.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                      {s.name}
                    </a>
                  </td>
                  <td className="py-2">{s.regulator}</td>
                  <td className="py-2">{s.category}</td>
                  <td className="py-2 text-xs text-label-tertiary">
                    {s.last_fetched_at ? formatDate(s.last_fetched_at) : "never"}
                  </td>
                  <td className="py-2 text-xs text-label-tertiary max-w-[16rem] truncate">{s.last_status || "—"}</td>
                  <td className="py-2 text-right whitespace-nowrap">
                    <Button size="sm" variant="ghost" onClick={() => void toggle(s)} className="mr-1">
                      {s.enabled ? "Disable" : "Enable"}
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => void refreshOne(s)} disabled={busyId === s.id} className="mr-1">
                      {busyId === s.id ? "…" : "Refresh"}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => void remove(s)} className="text-red-500 hover:bg-red-500/10">
                      Delete
                    </Button>
                  </td>
                </tr>
              ))}
              {sources.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-3 text-sm text-label-tertiary">
                    No sources yet — add one above.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <DiscoverPanel onSaved={onChanged} />
    </div>
  );
}

function DiscoverPanel({ onSaved }: { onSaved: () => void }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<DiscoverResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [savingUrl, setSavingUrl] = useState<string | null>(null);

  async function search(e: React.FormEvent) {
    e.preventDefault();
    if (q.trim().length < 2) return;
    setLoading(true);
    setSearched(true);
    try {
      setResults(await api.discoverNews(q.trim()));
    } finally {
      setLoading(false);
    }
  }

  async function save(r: DiscoverResult) {
    setSavingUrl(r.url);
    try {
      await api.saveDiscovered({ url: r.url, title: r.title, regulator: "Web" });
      onSaved();
    } finally {
      setSavingUrl(null);
    }
  }

  return (
    <Card title="Discover" subtitle="Web-search for regulatory news and save relevant items to the feed.">
      <form className="flex gap-2" onSubmit={search}>
        <Input
          placeholder="e.g. RBI digital lending guidelines 2024"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="flex-1"
        />
        <Button type="submit" disabled={loading}>
          {loading ? "Searching…" : "Search"}
        </Button>
      </form>
      <div className="mt-3 space-y-2">
        {searched && !loading && results.length === 0 && (
          <div className="text-sm text-label-tertiary">No results (web search may be unavailable).</div>
        )}
        {results.map((r) => (
          <div key={r.url} className="flex items-start justify-between gap-3 border-b border-separator/20 pb-2">
            <div className="min-w-0">
              <a href={r.url} target="_blank" rel="noreferrer" className="text-sm font-medium text-accent hover:underline">
                {r.title || r.url}
              </a>
              <p className="text-xs text-label-tertiary truncate">{r.snippet}</p>
            </div>
            <Button size="sm" variant="secondary" onClick={() => void save(r)} disabled={savingUrl === r.url}>
              {savingUrl === r.url ? "Saving…" : "Save"}
            </Button>
          </div>
        ))}
      </div>
    </Card>
  );
}
