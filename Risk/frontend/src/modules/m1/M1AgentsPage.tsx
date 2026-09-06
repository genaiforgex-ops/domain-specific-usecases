import { useEffect, useState } from "react";
import { api, AgentDefaults, ClassificationAgent } from "../../api/client";
import { useAuth } from "../../app/AuthContext";
import { useToast } from "../../app/ToastContext";
import {
  PageHeader,
  Card,
  DataTable,
  Button,
  Badge,
  FormField,
  Input,
  Textarea,
  EmptyState,
} from "../../components/ui";

// A blank form; prompts are filled from the backend defaults when creating a new
// agent so it starts from exactly today's built-in behavior.
type AgentForm = {
  name: string;
  description: string;
  rbi_prompt: string;
  sebi_prompt: string;
  model_version: string;
  temperature: string; // kept as string for the input; parsed on save
};

const EMPTY_FORM: AgentForm = {
  name: "",
  description: "",
  rbi_prompt: "",
  sebi_prompt: "",
  model_version: "gemini-2.5-flash",
  temperature: "0",
};

export function M1AgentsPage() {
  const { user } = useAuth();
  const toast = useToast();
  const canManage = !!user?.roles.includes("admin");

  const [agents, setAgents] = useState<ClassificationAgent[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editing, setEditing] = useState<ClassificationAgent | "new" | null>(null);
  const [form, setForm] = useState<AgentForm>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);

  const load = () => {
    setLoadError(null);
    api
      .get<ClassificationAgent[]>("/m1/agents")
      .then(setAgents)
      .catch((err: Error) => setLoadError(err.message));
  };

  useEffect(() => {
    load();
  }, []);

  const openNew = async () => {
    // Prefill with the built-in defaults so the user tweaks from a working base.
    let defaults: AgentDefaults | null = null;
    try {
      defaults = await api.get<AgentDefaults>("/m1/agents/defaults");
    } catch {
      /* fall back to empty prompts if defaults can't load */
    }
    setForm({
      ...EMPTY_FORM,
      rbi_prompt: defaults?.rbi_prompt ?? "",
      sebi_prompt: defaults?.sebi_prompt ?? "",
      model_version: defaults?.model_version ?? EMPTY_FORM.model_version,
      temperature: String(defaults?.temperature ?? 0),
    });
    setEditing("new");
  };

  const openEdit = (a: ClassificationAgent) => {
    setForm({
      name: a.name,
      description: a.description ?? "",
      rbi_prompt: a.rbi_prompt,
      sebi_prompt: a.sebi_prompt,
      model_version: a.model_version,
      temperature: String(a.temperature),
    });
    setEditing(a);
  };

  const save = async () => {
    if (!form.name.trim() || !form.rbi_prompt.trim() || !form.sebi_prompt.trim()) return;
    setSubmitting(true);
    try {
      const payload = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        rbi_prompt: form.rbi_prompt,
        sebi_prompt: form.sebi_prompt,
        model_version: form.model_version.trim(),
        temperature: Number(form.temperature) || 0,
      };
      if (editing === "new") {
        await api.post<ClassificationAgent>("/m1/agents", payload);
        toast.success("Agent created.");
      } else if (editing) {
        await api.patch<ClassificationAgent>(`/m1/agents/${editing.id}`, payload);
        toast.success("Agent updated.");
      }
      setEditing(null);
      load();
    } catch (err) {
      toast.error((err as Error).message || "Couldn't save the agent.");
    } finally {
      setSubmitting(false);
    }
  };

  const archive = async (a: ClassificationAgent) => {
    try {
      await api.patch(`/m1/agents/${a.id}`, { is_active: false });
      toast.success("Agent archived.");
      load();
    } catch (err) {
      toast.error((err as Error).message || "Couldn't archive the agent.");
    }
  };

  const set = (k: keyof AgentForm, v: string) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <div>
      <PageHeader
        breadcrumb="M1 · Outsourcing"
        title="Classification Agents"
        subtitle="Save named prompt configurations for M1. Pick one or more on a new assessment to compare how different prompts classify the same proposal."
        action={
          canManage ? (
            <Button variant="primary" onClick={openNew}>
              New agent
            </Button>
          ) : undefined
        }
      />

      <Card>
        {loadError ? (
          <EmptyState
            title="Couldn't load agents"
            description={
              loadError.includes("Missing permission")
                ? "You don't have permission to view classification agents."
                : loadError
            }
          />
        ) : agents.length === 0 ? (
          <EmptyState
            title="No agents yet"
            description={canManage ? "Create one to start experimenting with prompts." : "A Risk Manager can create agents here."}
          />
        ) : (
          <DataTable>
            <thead>
              <tr>
                <th>Name</th>
                <th>Description</th>
                <th>Model</th>
                <th>Temp.</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((a) => (
                <tr key={a.id}>
                  <td><strong>{a.name}</strong></td>
                  <td>{a.description || <span style={{ color: "var(--slate-400)" }}>—</span>}</td>
                  <td><Badge variant="neutral">{a.model_version}</Badge></td>
                  <td>{a.temperature}</td>
                  <td style={{ display: "flex", gap: 8 }}>
                    {canManage ? (
                      <>
                        <Button size="sm" variant="secondary" onClick={() => openEdit(a)}>Edit</Button>
                        <Button size="sm" variant="danger" onClick={() => archive(a)}>Archive</Button>
                      </>
                    ) : (
                      <Button size="sm" variant="ghost" onClick={() => openEdit(a)}>View</Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        )}
      </Card>

      {editing && (
        <>
          <div className="clause-viewer-backdrop" onClick={() => setEditing(null)} aria-hidden="true" />
          <aside className="clause-viewer-panel" aria-label="Agent editor" style={{ padding: 20, overflowY: "auto" }}>
            <h2 className="card__title">{editing === "new" ? "New agent" : `Edit — ${editing.name}`}</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <FormField label="Name" required>
                <Input value={form.name} disabled={!canManage} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Strict outsourcing v2" />
              </FormField>
              <FormField label="Description">
                <Input value={form.description} disabled={!canManage} onChange={(e) => set("description", e.target.value)} placeholder="What is this agent for?" />
              </FormField>
              <div className="form-grid form-grid--2">
                <FormField label="Model" hint="Gemini model id">
                  <Input value={form.model_version} disabled={!canManage} onChange={(e) => set("model_version", e.target.value)} />
                </FormField>
                <FormField label="Temperature" hint="0 = reproducible; higher = more varied">
                  <Input type="number" min="0" max="2" step="0.1" value={form.temperature} disabled={!canManage} onChange={(e) => set("temperature", e.target.value)} />
                </FormField>
              </div>
              <FormField label="RBI prompt" required hint="Guidance for the RBI classification call">
                <Textarea rows={12} value={form.rbi_prompt} disabled={!canManage} onChange={(e) => set("rbi_prompt", e.target.value)} />
              </FormField>
              <FormField label="SEBI prompt" required hint="Guidance for the SEBI classification call">
                <Textarea rows={12} value={form.sebi_prompt} disabled={!canManage} onChange={(e) => set("sebi_prompt", e.target.value)} />
              </FormField>
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
              {canManage && (
                <Button
                  variant="primary"
                  onClick={save}
                  loading={submitting}
                  disabled={!form.name.trim() || !form.rbi_prompt.trim() || !form.sebi_prompt.trim()}
                >
                  {submitting ? "Saving…" : editing === "new" ? "Create agent" : "Save changes"}
                </Button>
              )}
              <Button variant="ghost" onClick={() => setEditing(null)}>Close</Button>
            </div>
          </aside>
        </>
      )}
    </div>
  );
}
