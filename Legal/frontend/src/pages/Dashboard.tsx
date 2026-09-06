import { useEffect, useMemo, useState } from "react";
import type { ComponentType, SVGProps } from "react";
import { Link } from "react-router-dom";

import { Icon, LawGenieMark } from "@/components/Icons";
import { PageHeader } from "@/components/ui/PageHeader";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { hasPermission, roleLabel } from "@/lib/auth";
import { classNames, formatDate } from "@/lib/utils";
import type { AuditLogEntry, MetricsSummary, Permission } from "@/types";

type IconCmp = ComponentType<SVGProps<SVGSVGElement>>;

interface Module {
  to: string;
  title: string;
  blurb: string;
  perm: Permission;
  icon: IconCmp;
}

const MODULES: Module[] = [
  {
    to: "/tasks",
    title: "Task Manager",
    blurb: "AI-curated daily brief, Gmail-extracted tasks, and cross-module priorities.",
    perm: "task_management",
    icon: Icon.Inbox,
  },
  {
    to: "/build-studio",
    title: "Build Studio",
    blurb: "Submit a request, agent opens a PR on GitHub, human approves, auto-deploy.",
    perm: "build_requests",
    icon: Icon.Rocket,
  },
  {
    to: "/document-comparison",
    title: "Document Comparison",
    blurb: "Upload two PDF/DOCX/TXT files for a side-by-side diff with material-change risk flags.",
    perm: "document_comparison",
    icon: Icon.Compare,
  },
  {
    to: "/jiolegal",
    title: "LawGenie",
    blurb: "Conversational assistant — review documents, research, and draft, with citations.",
    perm: "legal_bot_use",
    icon: LawGenieMark,
  },
  {
    to: "/msa-automation",
    title: "Contract Automation",
    blurb: "End-to-end vendor contract workflow with email integration.",
    perm: "msa_automation",
    icon: Icon.Workflow,
  },
  {
    to: "/legal-news",
    title: "Regulatory Intelligence",
    blurb: "Live tracking of RBI, SEBI, IRDAI, DPDP & financial-sector updates.",
    perm: "legal_news_full",
    icon: Icon.Radar,
  },
];

interface Stats {
  contracts: number | null;
  comparisons: number | null;
  queries: number | null;
  research: number | null;
  msa: number | null;
  newsActionRequired: number | null;
}

function useStats() {
  const [stats, setStats] = useState<Stats>({
    contracts: null,
    comparisons: null,
    queries: null,
    research: null,
    msa: null,
    newsActionRequired: null,
  });
  useEffect(() => {
    let cancelled = false;
    async function load() {
      const wrap = <T,>(p: Promise<T>) => p.then((v) => v).catch(() => null);
      const [contracts, comparisons, queries, research, msa, news] = await Promise.all([
        wrap(api.listContracts()),
        wrap(api.listComparisons()),
        wrap(api.myQueries()),
        wrap(api.listResearch()),
        wrap(api.listMSA()),
        wrap(api.listNews({ status: "action_required" })),
      ]);
      if (cancelled) return;
      setStats({
        contracts: contracts ? contracts.length : null,
        comparisons: comparisons ? comparisons.length : null,
        queries: queries ? queries.length : null,
        research: research ? research.length : null,
        msa: msa ? msa.length : null,
        newsActionRequired: news ? news.length : null,
      });
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);
  return stats;
}

function useRecentActivity(): { entries: AuditLogEntry[]; loading: boolean } {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api
      .listAudit({ limit: 8 })
      .then((rows) => setEntries(rows))
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, []);
  return { entries, loading };
}

function useGovernanceMetrics(enabled: boolean) {
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [loading, setLoading] = useState(enabled);
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    api
      .getMetricsSummary()
      .then((m) => {
        if (!cancelled) setMetrics(m);
      })
      .catch(() => {
        if (!cancelled) setMetrics(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);
  return { metrics, loading };
}

export function Dashboard() {
  const { user } = useAuth();
  const stats = useStats();
  const { entries, loading: activityLoading } = useRecentActivity();
  const isAdmin = hasPermission(user, "audit_log_all");
  const { metrics: govMetrics, loading: govLoading } = useGovernanceMetrics(isAdmin);

  const greeting = useMemo(() => {
    const h = new Date().getHours();
    if (h < 12) return "Good morning";
    if (h < 17) return "Good afternoon";
    return "Good evening";
  }, []);

  const today = useMemo(
    () =>
      new Date().toLocaleDateString("en-IN", {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
      }),
    [],
  );

  if (!user) return null;

  const firstName = user.full_name.split(" ")[0];

  return (
    <div className="space-y-8 pb-10">
      <PageHeader
        eyebrow={
          <span className="inline-flex items-center gap-2">
            <Icon.Sparkles className="w-4 h-4" aria-hidden />
            {today}
          </span>
        }
        title={`${greeting}, ${firstName}.`}
        subtitle={
          <>
            Your AI workspace for the JFPSL Legal function. Signed in as{" "}
            <span className="font-medium text-label">{roleLabel(user.role)}</span>. All AI activity
            here is corpus-bounded and audit-logged for regulatory readiness.
          </>
        }
      />

      {isAdmin && (
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-lg text-label tracking-tight">Governance overview</h2>
            <Link to="/metrics" className="text-caption text-accent hover:underline">
              View full Metrics Panel →
            </Link>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 md:gap-4">
            <GovKpi label="Users" value={govMetrics?.total_users} loading={govLoading} />
            <GovKpi label="Documents" value={govMetrics?.total_documents} loading={govLoading} />
            <GovKpi label="Queries" value={govMetrics?.total_queries} loading={govLoading} />
            <GovKpi label="Active Users" value={govMetrics?.active_users} loading={govLoading} />
            <GovKpi label="Tokens (30d)" value={govMetrics?.total_tokens} loading={govLoading} />
          </div>
        </section>
      )}

      {/* Stats */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
        <StatCard
          icon={Icon.Documents}
          label="Contracts in review"
          value={stats.contracts}
          delay={60}
          available={hasPermission(user, "contract_review")}
        />
        <StatCard
          icon={Icon.Chat}
          label={hasPermission(user, "approve_ai_output") ? "Your queries" : "Queries asked"}
          value={stats.queries}
          delay={120}
          available={hasPermission(user, "legal_bot_use")}
        />
        <StatCard
          icon={Icon.Workflow}
          label="Active vendor threads"
          value={stats.msa}
          delay={180}
          available={hasPermission(user, "msa_automation")}
        />
        <StatCard
          icon={Icon.Bolt}
          label="Action-required updates"
          value={stats.newsActionRequired}
          delay={240}
          available={hasPermission(user, "legal_news_full", "legal_news_digest")}
        />
      </section>

      {/* Main grid: modules + activity */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-lg text-label tracking-tight">Your workspace</h2>
            <span className="text-caption text-label-tertiary">
              {MODULES.filter((m) => hasPermission(user, m.perm)).length} modules available
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {MODULES.map((m, i) => {
              const allowed = hasPermission(user, m.perm);
              return (
                <ModuleTile key={m.to} module={m} allowed={allowed} delay={80 + i * 70} />
              );
            })}
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-lg text-label tracking-tight">Recent activity</h2>
            <Link to="/audit" className="text-caption text-accent hover:underline">
              View all
            </Link>
          </div>
          <ActivityFeed entries={entries} loading={activityLoading} />
          <GovernanceBanner />
        </div>
      </section>
    </div>
  );
}

function GovKpi({
  label,
  value,
  loading,
}: {
  label: string;
  value: number | undefined;
  loading: boolean;
}) {
  return (
    <div className="rounded-lg bg-paper border border-separator/40 p-4">
      <div className="text-caption font-medium uppercase tracking-[0.12em] text-label-tertiary">{label}</div>
      <div className="mt-2 font-display text-title-3 text-label tabular-nums">
        {loading ? (
          <div className="h-7 w-16 rounded bg-bg-secondary animate-shimmer" />
        ) : (
          (value ?? 0).toLocaleString()
        )}
      </div>
    </div>
  );
}

function StatCard({
  icon: I,
  label,
  value,
  delay,
  available,
}: {
  icon: IconCmp;
  label: string;
  value: number | null;
  delay: number;
  available: boolean;
}) {
  const display = !available ? "—" : value === null ? null : value.toLocaleString();
  return (
    <div
      className="group relative overflow-hidden rounded-lg bg-paper border border-separator/40 shadow-card p-4 transition-shadow animate-slide-up"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex items-start justify-between">
        <span className="text-caption font-medium text-label-secondary">{label}</span>
        <div className="rounded-md p-1.5 bg-accent/10 text-accent">
          <I className="w-4 h-4" />
        </div>
      </div>
      <div className="mt-3">
        {display === null ? (
          <div className="h-8 w-16 rounded bg-bg-secondary animate-shimmer" />
        ) : (
          <div className="font-display text-title-2 text-label tabular-nums">{display}</div>
        )}
      </div>
      {!available && (
        <div className="mt-1 text-[10px] uppercase tracking-wider text-label-tertiary">No access</div>
      )}
    </div>
  );
}

function ModuleTile({
  module,
  allowed,
  delay,
}: {
  module: Module;
  allowed: boolean;
  delay: number;
}) {
  const I = module.icon;
  const inner = (
    <div>
      <div className="flex items-start justify-between">
        <div
          className={classNames(
            "rounded-md p-2.5 bg-accent/10 text-accent transition-transform duration-300",
            allowed && "group-hover:scale-105",
          )}
        >
          <I className="w-5 h-5" />
        </div>
        {allowed ? (
          <Icon.ArrowRight className="w-5 h-5 text-label-tertiary transition-all duration-300 group-hover:text-accent group-hover:translate-x-1" />
        ) : (
          <span className="text-[10px] uppercase tracking-wider text-label-tertiary mt-1">
            Locked
          </span>
        )}
      </div>
      <h3
        className={classNames(
          "mt-4 font-display text-lg tracking-tight transition-colors",
          allowed ? "text-label group-hover:text-accent" : "text-label-secondary",
        )}
      >
        {module.title}
      </h3>
      <p className="mt-1 text-subheadline text-label-secondary leading-relaxed">{module.blurb}</p>
    </div>
  );

  const baseClass = classNames(
    "group relative overflow-hidden rounded-lg bg-paper border border-separator/40 p-5 transition-all duration-300 animate-slide-up",
    allowed
      ? "shadow-card hover:-translate-y-0.5 hover:border-accent/25 cursor-pointer"
      : "opacity-60 cursor-not-allowed",
  );

  if (!allowed) {
    return (
      <div className={baseClass} style={{ animationDelay: `${delay}ms` }}>
        {inner}
      </div>
    );
  }
  return (
    <Link to={module.to} className={baseClass} style={{ animationDelay: `${delay}ms` }}>
      {inner}
    </Link>
  );
}

function ActivityFeed({ entries, loading }: { entries: AuditLogEntry[]; loading: boolean }) {
  return (
    <div className="rounded-lg bg-paper border border-separator/40 shadow-card divide-y divide-separator/30 animate-fade-in">
      {loading && (
        <div className="p-4 space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-bg-secondary animate-shimmer" />
              <div className="flex-1 space-y-1">
                <div className="h-3 w-3/4 rounded bg-bg-secondary" />
                <div className="h-2.5 w-1/3 rounded bg-bg-secondary" />
              </div>
            </div>
          ))}
        </div>
      )}
      {!loading && entries.length === 0 && (
        <div className="p-6 text-subheadline text-label-secondary text-center">No activity yet.</div>
      )}
      {!loading &&
        entries.map((e, idx) => (
          <div
            key={e.id}
            className="px-4 py-3 flex items-start gap-3 hover:bg-bg-secondary transition-colors animate-slide-up"
            style={{ animationDelay: `${idx * 40}ms` }}
          >
            <div className="w-8 h-8 rounded-full bg-accent/10 text-accent flex items-center justify-center shrink-0">
              <Icon.Activity className="w-4 h-4" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-subheadline text-label truncate">
                <span className="font-medium">{prettify(e.action_type)}</span>
                <span className="text-label-tertiary mx-1.5">·</span>
                <span className="text-label-secondary">{prettify(e.module)}</span>
              </div>
              <div className="text-[11px] text-label-tertiary mt-0.5 flex items-center gap-1.5">
                <Icon.Clock className="w-3 h-3" />
                <span>{formatDate(e.timestamp)}</span>
                {e.confidence_score != null && (
                  <>
                    <span>·</span>
                    <span>conf {Math.round(e.confidence_score * 100)}%</span>
                  </>
                )}
                {e.human_decision && (
                  <>
                    <span>·</span>
                    <span className="text-label-secondary">{e.human_decision}</span>
                  </>
                )}
              </div>
            </div>
          </div>
        ))}
    </div>
  );
}

function GovernanceBanner() {
  return (
    <div className="rounded-lg border border-separator/40 bg-paper p-4 animate-fade-in">
      <div className="flex items-start gap-3">
        <div className="rounded-md bg-ink text-white p-2 shrink-0">
          <Icon.Shield className="w-5 h-5" />
        </div>
        <div className="min-w-0">
          <p className="font-display text-base text-label tracking-tight">AI governance is on</p>
          <p className="text-caption text-label-secondary mt-1 leading-relaxed">
            Human-in-the-loop on every output, no external LLM calls for legal data, immutable
            7-year audit trail.
          </p>
        </div>
      </div>
    </div>
  );
}

function prettify(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
