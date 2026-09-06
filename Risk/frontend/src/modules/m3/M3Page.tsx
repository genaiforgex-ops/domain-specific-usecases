import { useEffect, useState } from "react";
import { api, Project, RiskScore } from "../../api/client";
import {
  PageHeader,
  Card,
  Button,
  FormField,
  Input,
  DataTable,
  Tabs,
  Gauge,
  Badge,
  EmptyState,
} from "../../components/ui";
import { riskBand } from "../../utils/format";
import { RiskBadge } from "../../components/ui/index";

const FACTORS: { key: string; label: string; hint: string }[] = [
  { key: "customer_impact", label: "Customer impact", hint: "Scale 1–5" },
  { key: "data_sensitivity", label: "Data sensitivity", hint: "PII / financial data exposure" },
  { key: "transaction_volume", label: "Transaction volume", hint: "Throughput / value" },
  { key: "vendor_dependency", label: "Vendor dependency", hint: "Third-party reliance" },
  { key: "regulatory_exposure", label: "Regulatory exposure", hint: "RBI / SEBI applicability" },
  { key: "technology_complexity", label: "Technology complexity", hint: "Architecture / change risk" },
];

export function M3Page() {
  const [tab, setTab] = useState("projects");
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<Project | null>(null);
  const [score, setScore] = useState<RiskScore | null>(null);
  const [whatIf, setWhatIf] = useState<{ residual_score: number; inherent_score: number } | null>(null);
  const [form, setForm] = useState({
    name: "",
    business_line: "Retail Banking",
    intake_data: Object.fromEntries(FACTORS.map((f) => [f.key, 3])) as Record<string, number>,
  });

  const load = () => api.get<Project[]>("/projects").then(setProjects);

  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.name) return;
    await api.post("/projects", form);
    setForm({
      name: "",
      business_line: "Retail Banking",
      intake_data: Object.fromEntries(FACTORS.map((f) => [f.key, 3])) as Record<string, number>,
    });
    load();
  };

  const compute = async (project: Project) => {
    setSelected(project);
    const s = await api.post<RiskScore>(`/projects/${project.id}/score`, {});
    setScore(s);
    setWhatIf(null);
    setTab("score");
  };

  const runWhatIf = async () => {
    if (!selected) return;
    const r = await api.post<{ residual_score: number; inherent_score: number }>(
      `/projects/${selected.id}/what-if`,
      { control_outcomes: { "CTRL-001": "fail", "CTRL-002": "pass", "CTRL-003": "partial" } }
    );
    setWhatIf(r);
  };

  const inherent = score?.final_inherent_score ?? score?.inherent_score ?? 0;
  const residual = score?.final_residual_score ?? score?.residual_score ?? 0;
  const band = riskBand(inherent);

  return (
    <div>
      <PageHeader
        breadcrumb="M3 · Risk Scoring"
        title="Inherent & Residual Risk Scoring"
        subtitle="Deterministic scoring model — same inputs always produce the same score. Transparent factor weights."
      />

      <Tabs
        tabs={[
          { id: "projects", label: "Projects" },
          { id: "new", label: "New project" },
          { id: "score", label: "Score detail" },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === "new" && (
        <Card>
          <h2 className="card__title">Project intake</h2>
          <div className="form-grid form-grid--2">
            <FormField label="Project name" required>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </FormField>
            <FormField label="Business line">
              <Input value={form.business_line} onChange={(e) => setForm({ ...form, business_line: e.target.value })} />
            </FormField>
            {FACTORS.map((f) => (
              <FormField key={f.key} label={f.label} hint={f.hint}>
                <Input
                  type="number"
                  min={1}
                  max={5}
                  value={form.intake_data[f.key]}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      intake_data: { ...form.intake_data, [f.key]: Number(e.target.value) },
                    })
                  }
                />
              </FormField>
            ))}
          </div>
          <Button variant="primary" className="mt-16" onClick={create}>Create project</Button>
        </Card>
      )}

      {tab === "projects" && (
        <Card>
          {projects.length === 0 ? (
            <EmptyState title="No projects" action={<Button onClick={() => setTab("new")}>Create project</Button>} />
          ) : (
            <DataTable>
              <thead>
                <tr><th>Project</th><th>Business line</th><th>Status</th><th></th></tr>
              </thead>
              <tbody>
                {projects.map((p) => (
                  <tr key={p.id}>
                    <td><strong>{p.name}</strong></td>
                    <td>{p.business_line}</td>
                    <td><Badge variant="neutral">{p.status}</Badge></td>
                    <td style={{ display: "flex", gap: 8 }}>
                      <Button size="sm" variant="primary" onClick={() => compute(p)}>Score</Button>
                      <Button size="sm" variant="ghost" onClick={() => { setSelected(p); runWhatIf(); setTab("score"); }}>
                        What-if
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
          )}
        </Card>
      )}

      {tab === "score" && (
        <>
          {!score && !whatIf ? (
            <Card>
              <EmptyState title="Select a project to score" action={<Button onClick={() => setTab("projects")}>View projects</Button>} />
            </Card>
          ) : (
            <div className="grid-2">
              <Card>
                <h2 className="card__title">{selected?.name ?? "Project"}</h2>
                <div style={{ display: "flex", gap: 32, justifyContent: "center", flexWrap: "wrap", padding: "8px 0 4px" }}>
                  <Gauge score={inherent} max={25} caption="Inherent risk" />
                  <Gauge score={residual} max={25} caption="Residual risk" />
                </div>
                <div style={{ textAlign: "center", marginTop: 4 }}>
                  <span style={{ fontSize: 13, color: "var(--slate-500)" }}>Inherent band </span>
                  <RiskBadge level={band.level} />
                </div>
                {score?.drivers?.top_factors && (
                  <>
                    <h3 className="card__title mt-16">Top contributing factors</h3>
                    <ul className="factor-list">
                      {score.drivers.top_factors.map((d) => (
                        <li key={d.factor}>
                          <span>{d.factor.replace(/_/g, " ")}</span>
                          <span className="factor-list__weight">+{d.contribution}</span>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </Card>
              <Card>
                <h3 className="card__title">What-if analysis</h3>
                <p style={{ fontSize: 14, color: "var(--slate-600)", margin: "0 0 16px" }}>
                  Sample scenario: KYC control fail, encryption pass, SLA partial.
                </p>
                <Button variant="secondary" onClick={runWhatIf} disabled={!selected}>
                  Run what-if
                </Button>
                {whatIf && (
                  <div style={{ marginTop: 20 }}>
                    <p style={{ margin: "0 0 8px" }}>Projected inherent: <strong>{whatIf.inherent_score}</strong></p>
                    <p style={{ margin: 0 }}>Projected residual: <strong>{whatIf.residual_score}</strong></p>
                  </div>
                )}
              </Card>
            </div>
          )}
        </>
      )}
    </div>
  );
}
