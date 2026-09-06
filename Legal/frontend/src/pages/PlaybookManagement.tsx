import { useEffect, useState } from "react";

import { ContractTypeSelect } from "@/components/ContractTypeSelect";
import { Icon } from "@/components/Icons";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { hasPermission } from "@/lib/auth";
import type { ClauseBankEntry, PlaybookClause } from "@/types";

type Tab = "playbook" | "clause-bank";

type PlaybookForm = {
  clause_type: string;
  standard_position: string;
  fallback_text: string;
  is_required: boolean;
  insert_anchor_hint: string;
};

type ClauseBankForm = {
  clause_type: string;
  title: string;
  body_text: string;
  tier: string;
};

const emptyPlaybookForm = (): PlaybookForm => ({
  clause_type: "",
  standard_position: "",
  fallback_text: "",
  is_required: false,
  insert_anchor_hint: "",
});

const emptyClauseBankForm = (): ClauseBankForm => ({
  clause_type: "",
  title: "",
  body_text: "",
  tier: "preferred",
});

export function PlaybookManagementPage() {
  const { user } = useAuth();
  const canEdit = hasPermission(user, "playbook_management");
  const [tab, setTab] = useState<Tab>("playbook");
  const [contractType, setContractType] = useState("MSA");
  const [clauses, setClauses] = useState<PlaybookClause[]>([]);
  const [bank, setBank] = useState<ClauseBankEntry[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const [c, b] = await Promise.all([
        api.listPlaybookClauses(contractType),
        api.listClauseBank(contractType),
      ]);
      setClauses(c.filter((x) => x.contract_type === contractType || x.contract_type === "ANY"));
      setBank(b);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [contractType]);

  return (
    <div className="space-y-6 pb-10 max-w-5xl">
      <PageHeader
        title="Playbook & clause bank"
        subtitle="Manage standard positions, fallback language, and insert-ready clauses. Edit or delete entries as requirements change."
      />

      <div className="flex flex-wrap items-end gap-4">
        <ContractTypeSelect value={contractType} onChange={setContractType} />
        <div className="flex gap-1 border border-separator/40 rounded-lg p-0.5">
          {(["playbook", "clause-bank"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 text-sm rounded-md capitalize ${
                tab === t ? "bg-accent/10 text-accent" : "text-label-secondary"
              }`}
            >
              {t.replace("-", " ")}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-label-secondary">Loading…</p>
      ) : tab === "playbook" ? (
        <PlaybookTab clauses={clauses} canEdit={canEdit} contractType={contractType} onSaved={load} />
      ) : (
        <ClauseBankTab entries={bank} canEdit={canEdit} contractType={contractType} onSaved={load} />
      )}
    </div>
  );
}

function PlaybookTab({
  clauses,
  canEdit,
  contractType,
  onSaved,
}: {
  clauses: PlaybookClause[];
  canEdit: boolean;
  contractType: string;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<PlaybookForm>(emptyPlaybookForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function startEdit(c: PlaybookClause) {
    setEditingId(c.id);
    setError(null);
    setForm({
      clause_type: c.clause_type,
      standard_position: c.standard_position,
      fallback_text: c.fallback_text || "",
      is_required: c.is_required,
      insert_anchor_hint: c.insert_anchor_hint || "",
    });
  }

  function cancelEdit() {
    setEditingId(null);
    setForm(emptyPlaybookForm());
    setError(null);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      if (editingId != null) {
        await api.updatePlaybookClause(editingId, {
          ...form,
          contract_type: contractType,
          fallback_text: form.fallback_text || null,
          insert_anchor_hint: form.insert_anchor_hint || null,
        });
      } else {
        await api.createPlaybookClause({
          ...form,
          contract_type: contractType,
          risk_keywords: [],
          regulatory_tags: [],
          fallback_text: form.fallback_text || null,
          insert_anchor_hint: form.insert_anchor_hint || null,
        });
      }
      cancelEdit();
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(c: PlaybookClause) {
    if (!window.confirm(`Delete playbook position “${c.clause_type}”? This cannot be undone.`)) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.deletePlaybookClause(c.id);
      if (editingId === c.id) cancelEdit();
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {canEdit && (
        <Card title={editingId != null ? "Edit playbook position" : "Add playbook position"}>
          <div className="space-y-3">
            <Input
              label="Clause type"
              value={form.clause_type}
              onChange={(e) => setForm({ ...form, clause_type: e.target.value })}
            />
            <Textarea
              label="Standard position"
              rows={4}
              value={form.standard_position}
              onChange={(e) => setForm({ ...form, standard_position: e.target.value })}
            />
            <Textarea
              label="Fallback text"
              rows={3}
              value={form.fallback_text}
              onChange={(e) => setForm({ ...form, fallback_text: e.target.value })}
            />
            <Input
              label="Insert anchor hint"
              value={form.insert_anchor_hint}
              onChange={(e) => setForm({ ...form, insert_anchor_hint: e.target.value })}
            />
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.is_required}
                onChange={(e) => setForm({ ...form, is_required: e.target.checked })}
              />
              Required clause
            </label>
            {error && <p className="text-sm text-error">{error}</p>}
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={() => void save()}
                disabled={busy || !form.clause_type || !form.standard_position}
              >
                {busy ? "Saving…" : editingId != null ? "Save changes" : "Add position"}
              </Button>
              {editingId != null && (
                <Button variant="secondary" onClick={cancelEdit} disabled={busy}>
                  Cancel
                </Button>
              )}
            </div>
          </div>
        </Card>
      )}
      <Card title={`Positions (${clauses.length})`}>
        {clauses.length === 0 ? (
          <p className="text-sm text-label-secondary py-2">No playbook positions for this contract type yet.</p>
        ) : (
          <ul className="divide-y divide-separator/30">
            {clauses.map((c) => (
              <li key={c.id} className="py-3 flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-label">{c.clause_type}</span>
                    {c.is_required && (
                      <span className="text-[10px] uppercase tracking-wide text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded">
                        Required
                      </span>
                    )}
                    {editingId === c.id && (
                      <span className="text-[10px] uppercase tracking-wide text-accent bg-accent/10 px-1.5 py-0.5 rounded">
                        Editing
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-label-secondary mt-1 whitespace-pre-wrap">{c.standard_position}</p>
                  {c.fallback_text && (
                    <p className="text-xs text-accent mt-1 whitespace-pre-wrap">Fallback: {c.fallback_text}</p>
                  )}
                </div>
                {canEdit && (
                  <div className="flex shrink-0 gap-1">
                    <button
                      type="button"
                      className="rounded-md px-2.5 py-1.5 text-xs font-medium text-accent hover:bg-accent/10"
                      onClick={() => startEdit(c)}
                      disabled={busy}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-xs font-medium text-error hover:bg-error/10"
                      onClick={() => void remove(c)}
                      disabled={busy}
                      title="Delete"
                    >
                      <Icon.Trash className="w-3.5 h-3.5" aria-hidden />
                      Delete
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function ClauseBankTab({
  entries,
  canEdit,
  contractType,
  onSaved,
}: {
  entries: ClauseBankEntry[];
  canEdit: boolean;
  contractType: string;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<ClauseBankForm>(emptyClauseBankForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function startEdit(e: ClauseBankEntry) {
    setEditingId(e.id);
    setError(null);
    setForm({
      clause_type: e.clause_type,
      title: e.title,
      body_text: e.body_text,
      tier: e.tier,
    });
  }

  function cancelEdit() {
    setEditingId(null);
    setForm(emptyClauseBankForm());
    setError(null);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      if (editingId != null) {
        await api.updateClauseBankEntry(editingId, { ...form, contract_type: contractType });
      } else {
        await api.createClauseBankEntry({ ...form, contract_type: contractType });
      }
      cancelEdit();
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(e: ClauseBankEntry) {
    if (!window.confirm(`Delete clause bank entry “${e.title}”? This cannot be undone.`)) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.deleteClauseBankEntry(e.id);
      if (editingId === e.id) cancelEdit();
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {canEdit && (
        <Card title={editingId != null ? "Edit clause bank entry" : "Add clause bank entry"}>
          <div className="space-y-3">
            <Input
              label="Clause type"
              value={form.clause_type}
              onChange={(e) => setForm({ ...form, clause_type: e.target.value })}
            />
            <Input
              label="Title"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
            <select
              className="w-full border border-separator/40 rounded-lg px-3 py-2 text-sm"
              value={form.tier}
              onChange={(e) => setForm({ ...form, tier: e.target.value })}
            >
              <option value="preferred">Preferred</option>
              <option value="fallback">Fallback</option>
              <option value="escalation">Escalation</option>
            </select>
            <Textarea
              label="Body text"
              rows={5}
              value={form.body_text}
              onChange={(e) => setForm({ ...form, body_text: e.target.value })}
            />
            {error && <p className="text-sm text-error">{error}</p>}
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => void save()} disabled={busy || !form.title || !form.body_text}>
                {busy ? "Saving…" : editingId != null ? "Save changes" : "Add entry"}
              </Button>
              {editingId != null && (
                <Button variant="secondary" onClick={cancelEdit} disabled={busy}>
                  Cancel
                </Button>
              )}
            </div>
          </div>
        </Card>
      )}
      <Card title={`Clause bank (${entries.length})`}>
        {entries.length === 0 ? (
          <p className="text-sm text-label-secondary py-2">No clause bank entries for this contract type yet.</p>
        ) : (
          <ul className="divide-y divide-separator/30">
            {entries.map((e) => (
              <li key={e.id} className="py-3 flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap gap-2 items-center">
                    <span className="font-medium text-label">{e.title}</span>
                    <span className="text-[10px] uppercase text-label-secondary">{e.tier}</span>
                    {editingId === e.id && (
                      <span className="text-[10px] uppercase tracking-wide text-accent bg-accent/10 px-1.5 py-0.5 rounded">
                        Editing
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-label-secondary">{e.clause_type}</p>
                  <p className="text-xs mt-1 whitespace-pre-wrap">{e.body_text}</p>
                </div>
                {canEdit && (
                  <div className="flex shrink-0 gap-1">
                    <button
                      type="button"
                      className="rounded-md px-2.5 py-1.5 text-xs font-medium text-accent hover:bg-accent/10"
                      onClick={() => startEdit(e)}
                      disabled={busy}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-xs font-medium text-error hover:bg-error/10"
                      onClick={() => void remove(e)}
                      disabled={busy}
                      title="Delete"
                    >
                      <Icon.Trash className="w-3.5 h-3.5" aria-hidden />
                      Delete
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
