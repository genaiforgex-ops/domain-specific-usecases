import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { StatCard, Card, DataTable } from "../components/ui";
import { IconShield, IconBuilding, IconChart, IconQueue, IconSparkle } from "../components/ui/Icons";

type TrendRow = { business_line: string; avg_inherent: number; avg_residual: number; count: number };

// Self-contained SVG grouped bar chart (no chart library). Bars grow in on
// mount and carry native tooltips. Categorical data → bars, not a line.
function BusinessLineChart({ data }: { data: TrendRow[] }) {
  const [grown, setGrown] = useState(false);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setGrown(true);
      return;
    }
    const id = requestAnimationFrame(() => setGrown(true));
    return () => cancelAnimationFrame(id);
  }, []);

  // Fixed viewBox so the rendered aspect ratio never depends on how many
  // business lines came back — groups divide the plot width instead.
  const W = 640, H = 280;
  const padL = 40, padR = 16, padT = 26, padB = 48;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const groupW = plotW / data.length;
  const barW = Math.max(4, Math.min(48, (groupW - 16) / 2 - 6));
  const barGap = Math.min(12, barW * 0.4);
  const maxChars = Math.max(6, Math.floor(groupW / 7));

  const rawMax = Math.max(...data.flatMap((d) => [d.avg_inherent, d.avg_residual]), 1);
  const step = rawMax <= 5 ? 1 : rawMax <= 10 ? 2 : rawMax <= 25 ? 5 : Math.ceil(rawMax / 25) * 5;
  const niceMax = Math.ceil(rawMax / step) * step;
  const y0 = padT + plotH;
  const scaleY = (v: number) => (v / niceMax) * plotH;
  const ticks = Array.from({ length: niceMax / step + 1 }, (_, i) => i * step);

  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Inherent and residual risk by business line">
        <defs>
          <linearGradient id="barInherent" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-accent)" />
            <stop offset="100%" stopColor="var(--color-highlight)" />
          </linearGradient>
          <linearGradient id="barResidual" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-ai)" />
            <stop offset="100%" stopColor="#a8d3fd" />
          </linearGradient>
        </defs>
        {ticks.map((t, i) => {
          const y = y0 - scaleY(t);
          return (
            <g key={i}>
              <line className="chart__grid" x1={padL} y1={y} x2={W - padR} y2={y} />
              <text className="chart__axis-label" x={padL - 8} y={y + 3} textAnchor="end">{t}</text>
            </g>
          );
        })}
        {data.map((d, i) => {
          const gx = padL + i * groupW + (groupW - (2 * barW + barGap)) / 2;
          const ih = scaleY(d.avg_inherent);
          const rh = scaleY(d.avg_residual);
          const label =
            d.business_line.length > maxChars ? d.business_line.slice(0, maxChars - 1) + "…" : d.business_line;
          return (
            <g key={d.business_line}>
              <rect className="chart__bar" x={gx} width={barW} rx={4}
                y={grown ? y0 - ih : y0} height={grown ? ih : 0} fill="url(#barInherent)">
                <title>{`${d.business_line} — inherent ${d.avg_inherent}`}</title>
              </rect>
              <rect className="chart__bar" x={gx + barW + barGap} width={barW} rx={4}
                y={grown ? y0 - rh : y0} height={grown ? rh : 0} fill="url(#barResidual)">
                <title>{`${d.business_line} — residual ${d.avg_residual}`}</title>
              </rect>
              {grown && (
                <>
                  <text className="chart__value" x={gx + barW / 2} y={y0 - ih - 7} textAnchor="middle">
                    {d.avg_inherent}
                  </text>
                  <text className="chart__value" x={gx + barW * 1.5 + barGap} y={y0 - rh - 7} textAnchor="middle">
                    {d.avg_residual}
                  </text>
                </>
              )}
              <text className="chart__xlabel" x={gx + barW + barGap / 2} y={y0 + 22} textAnchor="middle">
                {label}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="chart__legend">
        <span><i className="chart__dot" style={{ background: "var(--color-accent)" }} /> Inherent</span>
        <span><i className="chart__dot" style={{ background: "var(--color-ai)" }} /> Residual</span>
      </div>
    </div>
  );
}

export function HomePage() {
  const [metrics, setMetrics] = useState<Record<string, number> | null>(null);
  const [trends, setTrends] = useState<{
    by_business_line: Array<{ business_line: string; avg_inherent: number; avg_residual: number; count: number }>;
  } | null>(null);

  useEffect(() => {
    api.get<Record<string, number>>("/dashboards/operational").then(setMetrics).catch(() => {});
    api
      .get<{ by_business_line: Array<{ business_line: string; avg_inherent: number; avg_residual: number; count: number }> }>(
        "/dashboards/risk-trends"
      )
      .then(setTrends)
      .catch(() => {});
  }, []);

  return (
    <div>
      <section className="hero">
        <div className="hero__content">
          <span className="hero__crumb"><IconSparkle size={14} /> Workspace</span>
          <h1>Risk Command Center</h1>
          <p>
            One operational view across outsourcing classification, vendor due diligence,
            and project risk scoring — with AI working alongside every step.
          </p>
        </div>
        <div className="hero__actions">
          <Link to="/m2" className="btn btn--primary btn--md">
            <IconBuilding size={18} /> New due diligence
          </Link>
          <Link to="/queue" className="btn btn--secondary btn--md">
            <IconQueue size={18} /> View my queue
          </Link>
        </div>
      </section>

      <div className="stat-grid">
        <StatCard
          label="M1 Review queue"
          value={metrics?.m1_queue_depth ?? "—"}
          hint={`${metrics?.m1_override_rate_pct ?? 0}% AI override rate`}
          icon={<IconQueue size={20} />}
          accent="blue"
        />
        <StatCard
          label="M2 Open DD reports"
          value={metrics?.m2_open_reports ?? "—"}
          hint="Vendors awaiting sign-off"
          icon={<IconBuilding size={20} />}
          accent="amber"
        />
        <StatCard
          label="M3 Draft scores"
          value={metrics?.m3_draft_scores ?? "—"}
          hint="Projects pending confirmation"
          icon={<IconChart size={20} />}
          accent="emerald"
        />
      </div>

      <div className="grid-2 mb-24">
        <Card>
          <h2 className="card__title">Inherent vs residual by business line</h2>
          {trends && trends.by_business_line.length > 0 ? (
            <BusinessLineChart data={trends.by_business_line} />
          ) : (
            <p style={{ color: "var(--slate-500)", margin: 0 }}>Score projects in M3 to see trends.</p>
          )}
        </Card>

        <Card>
          <h2 className="card__title">Start a workflow</h2>
          <div className="quick-actions" style={{ gridTemplateColumns: "1fr" }}>
            <Link to="/m1" className="quick-action">
              <span className="quick-action__icon"><IconShield size={24} /></span>
              <div>
                <h3>Outsourcing classification</h3>
                <p>Classify vendor assessments against RBI / SEBI clauses</p>
              </div>
            </Link>
            <Link to="/m2" className="quick-action">
              <span className="quick-action__icon"><IconBuilding size={24} /></span>
              <div>
                <h3>Vendor due diligence</h3>
                <p>OSINT screening, red-flag score, DD report export</p>
              </div>
            </Link>
            <Link to="/m3" className="quick-action">
              <span className="quick-action__icon"><IconChart size={24} /></span>
              <div>
                <h3>Risk scoring</h3>
                <p>Inherent & residual scores with what-if analysis</p>
              </div>
            </Link>
          </div>
        </Card>
      </div>

      {trends && trends.by_business_line.length > 0 && (
        <Card>
          <div className="card__header">
            <h2 className="card__title" style={{ margin: 0 }}>Portfolio summary</h2>
            <Link to="/m3">View all projects →</Link>
          </div>
          <DataTable>
            <thead>
              <tr>
                <th>Business line</th>
                <th>Avg inherent</th>
                <th>Avg residual</th>
                <th>Projects</th>
              </tr>
            </thead>
            <tbody>
              {trends.by_business_line.map((r) => (
                <tr key={r.business_line}>
                  <td><strong>{r.business_line}</strong></td>
                  <td>{r.avg_inherent}</td>
                  <td>{r.avg_residual}</td>
                  <td>{r.count}</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </Card>
      )}
    </div>
  );
}
