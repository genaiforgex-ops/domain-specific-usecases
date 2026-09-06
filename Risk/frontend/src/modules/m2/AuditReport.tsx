import { useState } from "react";
import { AuditData } from "../../api/client";
import { Card, Badge, DataTable, Tabs } from "../../components/ui";

const ratingColor = (rating?: string): string => {
  switch ((rating || "").toLowerCase()) {
    case "critical": return "var(--red-600, #dc2626)";
    case "high": return "var(--red-500, #ef4444)";
    case "medium": return "var(--amber-500, #f59e0b)";
    case "low": return "var(--green-600, #16a34a)";
    default: return "var(--slate-400, #94a3b8)";
  }
};

const decisionVariant = (decision?: string): "success" | "warning" | "danger" | "neutral" => {
  const d = (decision || "").toLowerCase();
  if (d.includes("reject")) return "danger";
  if (d.includes("condition") || d.includes("manual")) return "warning";
  if (d.includes("approve")) return "success";
  return "neutral";
};

// A compliance check can be a genuine pass, a genuine problem, or simply
// "not performed in this run" — the last must read as neutral, not a red failure.
const complianceTone = (status?: string): "good" | "bad" | "neutral" => {
  const s = (status || "").toLowerCase();
  if (["pass", "low", "clean", "ok", "verified"].includes(s)) return "good";
  if (["not run", "none", "n/a", "na", "pending", "unknown", ""].includes(s)) return "neutral";
  return "bad";
};

const bandForScore = (score?: number): string => {
  if (typeof score !== "number") return "—";
  if (score <= 25) return "Low";
  if (score <= 50) return "Medium";
  if (score <= 75) return "High";
  return "Critical";
};

/**
 * Turn an internal `_error` code into something a risk analyst can act on.
 *
 * These codes are diagnostic identifiers, not user-facing copy — showing
 * "unparseable_model_response" verbatim tells the reader nothing about what
 * went wrong or what to do next. Anything unrecognised (an adapter exception is
 * stored as its raw message) is passed through, since that text is at least
 * descriptive.
 */
const SCREENING_NOTES: Record<string, string> = {
  unparseable_model_response:
    "The screening model did not return a usable audit, so this report is empty. Re-run the screening.",
  truncated_model_response:
    "The screening model ran out of room before finishing the audit, so this report is empty. Re-run the screening.",
};

function screeningNote(code: string): string {
  return SCREENING_NOTES[code] ?? code;
}

function Pill({ text, tone }: { text: string; tone: "good" | "bad" | "neutral" }) {
  const bg = tone === "good" ? "#dcfce7" : tone === "bad" ? "#fee2e2" : "#f1f5f9";
  const fg = tone === "good" ? "#166534" : tone === "bad" ? "#991b1b" : "#334155";
  return (
    <span style={{ background: bg, color: fg, padding: "4px 10px", borderRadius: 999, fontSize: 12, fontWeight: 600, display: "inline-block" }}>
      {text}
    </span>
  );
}

// One consistent card-level heading (optionally with a colored dot), so the
// report stops mixing emoji headers, default h4s, and card titles.
function CardHeading({ dot, children }: { dot?: string; children: React.ReactNode }) {
  return (
    <h3 className="card__title" style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 0 }}>
      {dot && <span style={{ width: 10, height: 10, borderRadius: 3, background: dot, display: "inline-block", flexShrink: 0 }} />}
      {children}
    </h3>
  );
}

function Section({ title, children, count }: { title: string; children: React.ReactNode; count?: number }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <h4 style={{ margin: "0 0 10px", fontSize: 14, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--slate-500)" }}>
        {title}{typeof count === "number" ? ` (${count})` : ""}
      </h4>
      {children}
    </div>
  );
}

function KV({ label, value }: { label: string; value?: React.ReactNode }) {
  if (value === undefined || value === null || value === "") return null;
  return (
    <div style={{ display: "flex", gap: 8, fontSize: 14, padding: "4px 0" }}>
      <span style={{ color: "var(--slate-500)", minWidth: 140 }}>{label}</span>
      <span style={{ fontWeight: 500 }}>{value}</span>
    </div>
  );
}

export function AuditReport({ audit }: { audit: AuditData }) {
  const [sub, setSub] = useState("overview");
  const risk = audit.risk || {};
  const legal = audit.legal || {};
  const security = audit.security || {};
  const social = audit.social || {};
  const footprint = audit.footprint || {};

  const litigations = legal.litigations || [];
  const news = legal.news || [];
  const reputation = security.reputation_sources || {};
  const relations = footprint.discovered_relations || [];
  const domains = footprint.discovered_domains || [];

  return (
    <div>
      {/* Decision banner */}
      <Card className="mb-24">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{audit.business_name || audit._domain || "Vendor"}</div>
            <div style={{ color: "var(--slate-500)", fontSize: 14 }}>
              {audit.industry}{audit.industry && audit.country ? " · " : ""}{audit.country}
            </div>
            {audit.business_description && (
              <p style={{ marginTop: 8, fontSize: 14, maxWidth: 640 }}>{audit.business_description}</p>
            )}
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 12, color: "var(--slate-500)" }}>Recommendation</div>
            <div style={{ marginTop: 2 }}>
              <Badge variant={decisionVariant(risk.decision)}>{risk.decision || "—"}</Badge>
            </div>
            <div style={{ marginTop: 8 }}>
              <span style={{ fontSize: 28, fontWeight: 800, color: ratingColor(risk.rating) }}>
                {typeof risk.score === "number" ? Math.round(risk.score) : "—"}
              </span>
              <span style={{ color: "var(--slate-400)" }}>/100</span>
              <span style={{ marginLeft: 8, color: ratingColor(risk.rating), fontWeight: 700 }}>{risk.rating || bandForScore(risk.score)}</span>
            </div>
            <div style={{ fontSize: 11, color: "var(--slate-400)", marginTop: 4, maxWidth: 220 }}>
              Higher = riskier. 0–25 Low · 26–50 Medium · 51–75 High · 76–100 Critical
            </div>
          </div>
        </div>
        {risk.summary && <p style={{ marginTop: 12, fontSize: 14, color: "var(--slate-700)" }}>{risk.summary}</p>}
        {audit._error && (
          <p style={{ marginTop: 8, fontSize: 13, color: "#991b1b" }}>
            ⚠ Screening note: {screeningNote(audit._error)}
          </p>
        )}
      </Card>

      {/* Flags */}
      {((risk.red_flags?.length || 0) > 0 || (risk.green_flags?.length || 0) > 0) && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 16, alignItems: "stretch", marginBottom: 24 }}>
          <Card>
            <CardHeading dot="var(--color-error)">Red flags</CardHeading>
            {(risk.red_flags || []).length === 0 ? <p style={{ color: "var(--slate-500)" }}>None identified</p> :
              <ul style={{ margin: 0, paddingLeft: 18 }}>{(risk.red_flags || []).map((f, i) => <li key={i} style={{ marginBottom: 4 }}>{f}</li>)}</ul>}
          </Card>
          <Card>
            <CardHeading dot="var(--color-success)">Green flags</CardHeading>
            {(risk.green_flags || []).length === 0 ? <p style={{ color: "var(--slate-500)" }}>None identified</p> :
              <ul style={{ margin: 0, paddingLeft: 18 }}>{(risk.green_flags || []).map((f, i) => <li key={i} style={{ marginBottom: 4 }}>{f}</li>)}</ul>}
          </Card>
        </div>
      )}
      {(risk.conditions?.length || 0) > 0 && (
        <Card className="mb-24">
          <CardHeading>Conditions for approval</CardHeading>
          <ul style={{ margin: 0, paddingLeft: 18 }}>{(risk.conditions || []).map((c, i) => <li key={i}>{c}</li>)}</ul>
        </Card>
      )}

      <Card className="mb-24">
        <CardHeading>How this score was reached</CardHeading>
        <p style={{ fontSize: 13, color: "var(--slate-600)", marginTop: 0 }}>
          The screening agent researches the vendor across sanctions, litigation, adverse media, financial distress,
          ownership and security sources, then assigns a 0–100 risk score and a recommendation. Higher score = more or
          more-severe red flags.
        </p>
        {(risk.factors?.length || 0) > 0 ? (
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {(risk.factors as any[]).map((f, i) => {
              // The live model may return factors as plain strings or as
              // {factor, impact, points, detail} objects — handle both.
              if (typeof f === "string") return <li key={i} style={{ marginBottom: 6 }}>{f}</li>;
              const label = [f.factor, f.detail].filter(Boolean).join(" — ") || "Factor";
              const pts = typeof f.points === "number" ? ` (${f.points > 0 ? "+" : ""}${f.points} pts)` : "";
              return (
                <li key={i} style={{ marginBottom: 6 }}>
                  {label}{f.impact ? ` — impact: ${f.impact}` : ""}{pts}
                </li>
              );
            })}
          </ul>
        ) : (
          <p style={{ fontSize: 13, color: "var(--slate-500)", margin: 0 }}>
            No per-factor breakdown was provided for this run. The score reflects the
            red / green flags listed above.
          </p>
        )}
      </Card>

      <Tabs
        tabs={[
          { id: "overview", label: "Overview" },
          { id: "security", label: "Security & Reputation" },
          { id: "legal", label: `Legal (${litigations.length + news.length})` },
          { id: "compliance", label: "Compliance & Identity" },
          { id: "footprint", label: "Footprint" },
        ]}
        active={sub}
        onChange={setSub}
      />

      {sub === "overview" && (
        <Card>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 24 }}>
            <Section title="Identity">
              <KV label="Website" value={audit._url && <a href={audit._url} target="_blank" rel="noreferrer">{audit._url}</a>} />
              <KV label="SSL secure" value={audit.ssl_secure ? "Yes" : "No"} />
              <KV label="Mobile friendly" value={audit.mobile_friendly ? "Yes" : "No"} />
              <KV label="Payment gateway" value={audit.payment?.gateway} />
              {(audit.payment?.methods?.length || 0) > 0 && <KV label="Payment methods" value={audit.payment!.methods!.join(", ")} />}
            </Section>
            {audit.technical && (
              <Section title="Technical">
                <KV label="Platform" value={audit.technical.platform} />
                <KV label="Hosting" value={audit.technical.hosting} />
                <KV label="Domain registered" value={audit.technical.domain_registered} />
                <KV label="Domain age" value={audit.technical.domain_age} />
                {(audit.technical.analytics?.length || 0) > 0 && <KV label="Analytics" value={audit.technical.analytics!.join(", ")} />}
              </Section>
            )}
          </div>
          {(() => {
            const pages = (audit.key_pages || []) as any[];
            const pageUrl = (p: any) => (typeof p === "string" ? p : (p.url || p.page || ""));
            // Only show the Status/Snapshot table if the model actually
            // filled those in; otherwise just list the page links.
            const haveDetail = pages.some((p) => p && typeof p === "object" && (p.status || p.snapshot));
            if (pages.length === 0) return null; // "if nothing is coming, remove it"
            return (
              <Section title="Pages the agent checked" count={pages.length}>
                {haveDetail ? (
                  <DataTable>
                    <thead><tr><th>Page</th><th>Status</th><th>Snapshot</th></tr></thead>
                    <tbody>
                      {pages.map((p, i) => {
                        const url = pageUrl(p);
                        const status = typeof p === "object" ? (p.status || "") : "";
                        const snapshot = typeof p === "object" ? (p.snapshot || "") : "";
                        return (
                          <tr key={i}>
                            <td>{url ? <a href={url} target="_blank" rel="noreferrer">{url}</a> : (typeof p === "object" ? p.page : String(p))}</td>
                            <td>{status
                              ? <Pill text={status} tone={status.toLowerCase() === "found" ? "good" : status.toLowerCase().includes("not") ? "bad" : "neutral"} />
                              : <span style={{ color: "var(--slate-400)" }}>—</span>}</td>
                            <td style={{ fontSize: 13 }}>{snapshot || <span style={{ color: "var(--slate-400)" }}>—</span>}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </DataTable>
                ) : (
                  <ul style={{ margin: 0, paddingLeft: 18, columns: 2, columnGap: 32 }}>
                    {pages.map((p, i) => {
                      const url = pageUrl(p);
                      return (
                        <li key={i} style={{ marginBottom: 4, breakInside: "avoid" }}>
                          {url ? <a href={url} target="_blank" rel="noreferrer" style={{ fontSize: 13 }}>{url}</a> : <span style={{ fontSize: 13 }}>{String(p)}</span>}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </Section>
            );
          })()}
        </Card>
      )}

      {sub === "security" && (
        <Card>
          <Section title="Posture">
            <KV label="OWASP posture score" value={typeof security.owasp_posture_score === "number" ? `${security.owasp_posture_score}/100` : undefined} />
            <KV label="Security headers" value={audit.technical?.security_headers &&
              ["hsts", "csp", "xframe"].map(h => `${h.toUpperCase()}: ${(audit.technical!.security_headers as any)[h] ? "✓" : "✗"}`).join("  ")} />
            {security.notes && <KV label="Notes" value={security.notes} />}
          </Section>
          <Section title="Threat-intel reputation">
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {Object.entries(reputation).map(([src, d]) => (
                <Pill key={src} text={`${src}: ${d?.status || d?.level || ((d?.detections || 0) > 0 ? `${d.detections} hits` : "clean")}`}
                  tone={(d?.detections || 0) > 0 || ["high", "medium"].includes((d?.level || "").toLowerCase()) ? "bad" : "good"} />
              ))}
            </div>
          </Section>
          <Section title="VAPT findings" count={security.vapt_findings?.length || 0}>
            {(security.vapt_findings || []).length === 0 ? <p style={{ color: "var(--slate-500)" }}>None reported.</p> :
              (security.vapt_findings || []).map((v, i) => (
                <div key={i} className="finding-card" style={{ marginBottom: 8 }}>
                  <div className="finding-card__cat">{v.category} <Badge variant={["high", "critical"].includes((v.severity || "").toLowerCase()) ? "danger" : "neutral"}>{v.severity}</Badge></div>
                  <p style={{ margin: "4px 0" }}>{v.description}</p>
                  {v.recommendation && <p style={{ margin: 0, fontSize: 13, color: "var(--slate-600)" }}>Fix: {v.recommendation}</p>}
                </div>
              ))}
          </Section>
          <Section title="Incident history" count={security.incident_history?.length || 0}>
            {(security.incident_history || []).length === 0 ? <p style={{ color: "var(--slate-500)" }}>No incidents found.</p> :
              (security.incident_history || []).map((inc, i) => (
                <div key={i} style={{ fontSize: 14, padding: "6px 0", borderBottom: "1px solid var(--slate-100)" }}>
                  <strong>{inc.event}</strong> — {inc.status} <span style={{ color: "var(--slate-500)" }}>{inc.date}</span>
                  <div style={{ color: "var(--slate-600)" }}>{inc.summary}</div>
                </div>
              ))}
          </Section>
          <Section title="Social & online reputation">
            <div style={{ marginBottom: 8 }}>
              {social.reputation && <Pill text={`Reputation: ${social.reputation}`} tone={(social.reputation || "").toLowerCase().includes("neg") ? "bad" : (social.reputation || "").toLowerCase().includes("pos") ? "good" : "neutral"} />}
            </div>
            {social.review_summary && <p style={{ fontSize: 14, marginTop: 0 }}>{social.review_summary}</p>}
            {(social.profiles?.length || 0) > 0 ? (
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
                {(social.profiles as any[]).map((p, i) => {
                  const isStr = typeof p === "string";
                  const label = isStr ? p : [p.platform, p.handle, p.followers ? `${p.followers}` : null].filter(Boolean).join(" · ");
                  const url = isStr ? undefined : p.url;
                  const chip = { background: "#eef2ff", color: "#3730a3", padding: "5px 10px", borderRadius: 8, fontSize: 13, fontWeight: 500, textDecoration: "none" as const };
                  return url
                    ? <a key={i} href={url} target="_blank" rel="noreferrer" style={chip}>{label || url}</a>
                    : <span key={i} style={chip}>{label || String(p)}</span>;
                })}
              </div>
            ) : <p style={{ color: "var(--slate-500)" }}>No social profiles found.</p>}
          </Section>
        </Card>
      )}

      {sub === "legal" && (
        <Card>
          <Section title="Litigations" count={litigations.length}>
            {litigations.length === 0 ? <p style={{ color: "var(--slate-500)" }}>No litigation found in public records.</p> :
              (litigations as any[]).map((l, i) => typeof l === "string" ? (
                <div key={i} className="finding-card finding-card--high" style={{ marginBottom: 8 }}><p style={{ margin: 0 }}>{l}</p></div>
              ) : (
                <div key={i} className="finding-card finding-card--high" style={{ marginBottom: 8 }}>
                  <div className="finding-card__cat">{l.type || "Litigation"} {l.status && <Badge variant="danger">{l.status}</Badge>}</div>
                  <p style={{ margin: "4px 0" }}>{l.summary}</p>
                  <div style={{ fontSize: 13, color: "var(--slate-600)" }}>
                    {[l.parties, l.case_number, l.court, l.filing_date].filter(Boolean).join(" · ")}
                  </div>
                </div>
              ))}
          </Section>
          <Section title="Adverse & general news" count={news.length}>
            {news.length === 0 ? <p style={{ color: "var(--slate-500)" }}>No news found.</p> :
              (news as any[]).map((n, i) => typeof n === "string" ? (
                <div key={i} style={{ padding: "8px 0", borderBottom: "1px solid var(--slate-100)" }}><p style={{ margin: 0, fontSize: 14 }}>{n}</p></div>
              ) : (
                <div key={i} style={{ padding: "8px 0", borderBottom: "1px solid var(--slate-100)" }}>
                  <div style={{ fontWeight: 600 }}>{n.url ? <a href={n.url} target="_blank" rel="noreferrer">{n.headline}</a> : n.headline}</div>
                  <div style={{ fontSize: 13, color: "var(--slate-500)" }}>{[n.source, n.date].filter(Boolean).join(" · ")}</div>
                  <p style={{ margin: "4px 0 0", fontSize: 14 }}>{n.summary}</p>
                </div>
              ))}
          </Section>
          {legal.notes && <p style={{ fontSize: 13, color: "var(--slate-600)" }}>{legal.notes}</p>}
        </Card>
      )}

      {sub === "compliance" && (
        <Card>
          <Section title="Compliance checks">
            <p style={{ fontSize: 12, color: "var(--slate-500)", marginTop: 0 }}>
              <Pill text="Pass" tone="good" /> check passed &nbsp;·&nbsp;
              <Pill text="Fail" tone="bad" /> issue found &nbsp;·&nbsp;
              <Pill text="Not Run" tone="neutral" /> not performed in this run
            </p>
            <DataTable>
              <thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead>
              <tbody>
                {Object.entries(audit.compliance_checks || {}).map(([name, c]) => (
                  <tr key={name}>
                    <td style={{ textTransform: "capitalize" }}>{name.replace(/_/g, " ")}</td>
                    <td><Pill text={c?.status || "Not Run"} tone={complianceTone(c?.status)} /></td>
                    <td style={{ fontSize: 13 }}>
                      {c?.details || <span style={{ color: "var(--slate-400)" }}>—</span>}
                      {c?.registration_id && <div><strong>{c.registration_type || "ID"}:</strong> {c.registration_id}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
          </Section>
        </Card>
      )}

      {sub === "footprint" && (
        <Card>
          <Section title="Contact assets">
            <KV label="Emails" value={(footprint.contact_assets?.emails || []).join(", ")} />
            <KV label="Phones" value={(footprint.contact_assets?.phones || []).join(", ")} />
            <KV label="Addresses" value={(footprint.contact_assets?.addresses || []).join("; ")} />
          </Section>
          {relations.length > 0 && (() => {
            const rels = relations as any[];
            const entityName = (r: any) => (typeof r === "string" ? r : (r.entity_name || r.entity || r.name || ""));
            // Only show the full table when the model actually filled the
            // relationship/asset/risk columns; otherwise just list the names.
            const haveDetail = rels.some((r) => r && typeof r === "object" && (r.relationship_type || r.shared_asset || r.risk_rating));
            return (
              <Section title="Discovered related entities" count={rels.length}>
                {haveDetail ? (
                  <DataTable>
                    <thead><tr><th>Entity</th><th>Relationship</th><th>Shared asset</th><th>Risk</th></tr></thead>
                    <tbody>{rels.map((r, i) => (
                      <tr key={i}><td>{entityName(r)}</td><td>{r.relationship_type}</td><td style={{ fontSize: 13 }}>{r.shared_asset}</td>
                      <td>{r.risk_rating ? <Pill text={r.risk_rating} tone={["high", "critical", "medium"].includes((r.risk_rating || "").toLowerCase()) ? "bad" : "good"} /> : <span style={{ color: "var(--slate-400)" }}>—</span>}</td></tr>
                    ))}</tbody>
                  </DataTable>
                ) : (
                  <ul style={{ margin: 0, paddingLeft: 18, columns: 2, columnGap: 32 }}>
                    {rels.map((r, i) => <li key={i} style={{ marginBottom: 4, breakInside: "avoid" }}>{entityName(r) || String(r)}</li>)}
                  </ul>
                )}
              </Section>
            );
          })()}
          {domains.length > 0 && (() => {
            const doms = domains as any[];
            const domainName = (d: any) => (typeof d === "string" ? d : (d.domain || d.url || ""));
            const haveDetail = doms.some((d) => d && typeof d === "object" && (d.discovery_source || d.status));
            return (
              <Section title="Discovered domains" count={doms.length}>
                {haveDetail ? (
                  <DataTable>
                    <thead><tr><th>Domain</th><th>Discovered via</th><th>Status</th></tr></thead>
                    <tbody>{doms.map((d, i) => (
                      <tr key={i}><td className="mono">{domainName(d)}</td><td style={{ fontSize: 13 }}>{d.discovery_source}</td><td>{d.status}</td></tr>
                    ))}</tbody>
                  </DataTable>
                ) : (
                  <ul style={{ margin: 0, paddingLeft: 18, columns: 2, columnGap: 32 }}>
                    {doms.map((d, i) => <li key={i} className="mono" style={{ marginBottom: 4, breakInside: "avoid", fontSize: 13 }}>{domainName(d) || String(d)}</li>)}
                  </ul>
                )}
              </Section>
            );
          })()}
          {(audit._grounding_sources?.length || 0) > 0 && (
            <Section title="Grounded sources" count={audit._grounding_sources!.length}>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                {audit._grounding_sources!.slice(0, 20).map((s, i) => (
                  <li key={i}><a href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a></li>
                ))}
              </ul>
            </Section>
          )}
        </Card>
      )}
    </div>
  );
}
