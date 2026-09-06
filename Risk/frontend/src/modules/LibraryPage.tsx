import { useEffect, useState } from "react";
import { api, Clause, RegulationDocument } from "../api/client";
import { PageHeader, Card, DataTable, Button, Badge, FormField, Input, Select, EmptyState } from "../components/ui";

const STATUS_VARIANT: Record<RegulationDocument["status"], "neutral" | "success" | "warning" | "danger" | "info"> = {
  processing: "info",
  pending_review: "warning",
  active: "success",
  archived: "neutral",
  failed: "danger",
};

const STATUS_LABEL: Record<RegulationDocument["status"], string> = {
  processing: "Processing…",
  pending_review: "Pending review",
  active: "Active",
  archived: "Archived",
  failed: "Ingestion failed",
};

export function LibraryPage() {
  const [documents, setDocuments] = useState<RegulationDocument[]>([]);
  const [regulator, setRegulator] = useState("RBI");
  const [instrument, setInstrument] = useState("");
  const [sourceDoc, setSourceDoc] = useState("");
  const [refPrefix, setRefPrefix] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [reviewing, setReviewing] = useState<RegulationDocument | null>(null);
  const [reviewClauses, setReviewClauses] = useState<Clause[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = () => {
    setLoadError(null);
    api.get<RegulationDocument[]>("/library/documents")
      .then(setDocuments)
      .catch((err: Error) => setLoadError(err.message));
  };

  useEffect(() => {
    load();
  }, []);

  const pollUntilSettled = async (id: string) => {
    for (let i = 0; i < 15; i++) {
      const docs = await api.get<RegulationDocument[]>("/library/documents");
      setDocuments(docs);
      const doc = docs.find((d) => d.id === id);
      if (doc && doc.status !== "processing") return;
      await new Promise((r) => setTimeout(r, 800));
    }
  };

  const submit = async () => {
    if (!instrument || !sourceDoc || !refPrefix || !file) return;
    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append("regulator", regulator);
      fd.append("instrument", instrument);
      fd.append("source_doc", sourceDoc);
      fd.append("ref_prefix", refPrefix);
      fd.append("file", file);
      const doc = await api.upload<RegulationDocument>("/library/documents", fd);
      setInstrument("");
      setSourceDoc("");
      setRefPrefix("");
      setFile(null);
      await pollUntilSettled(doc.id);
    } finally {
      setSubmitting(false);
    }
  };

  const openReview = async (doc: RegulationDocument) => {
    setReviewing(doc);
    const clauses = await api.get<Clause[]>(`/library/documents/${doc.id}/clauses`);
    setReviewClauses(clauses);
  };

  const activate = async (id: string) => {
    await api.post(`/library/documents/${id}/activate`);
    setReviewing(null);
    load();
  };

  const archive = async (id: string) => {
    await api.post(`/library/documents/${id}/archive`);
    load();
  };

  return (
    <div>
      <PageHeader
        breadcrumb="Governance"
        title="Regulation Library"
        subtitle="Upload RBI/SEBI circulars directly — extracted clauses feed M1 classification without a developer release."
      />

      <Card className="mb-24">
        <h2 className="card__title">Upload a regulation PDF</h2>
        <div className="form-grid form-grid--2">
          <FormField label="Regulator" required>
            <Select value={regulator} onChange={(e) => setRegulator(e.target.value)}>
              <option value="RBI">RBI</option>
              <option value="SEBI">SEBI</option>
            </Select>
          </FormField>
          <FormField label="Instrument" required hint='e.g. "NBFC", "PAYMENTS_BANK", "IA"'>
            <Input value={instrument} onChange={(e) => setInstrument(e.target.value)} placeholder="NBFC" />
          </FormField>
          <FormField label="Source document title" required hint="Shown in citations">
            <Input
              value={sourceDoc}
              onChange={(e) => setSourceDoc(e.target.value)}
              placeholder="RBI (NBFC - Managing Risks in Outsourcing) Directions, 2026"
            />
          </FormField>
          <FormField label="Clause reference prefix" required hint='e.g. "RBI-NBFC-2026"'>
            <Input value={refPrefix} onChange={(e) => setRefPrefix(e.target.value)} placeholder="RBI-NBFC-2026" />
          </FormField>
          <FormField label="PDF file" required>
            <Input type="file" accept=".pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            {file && <div style={{ fontSize: 12, color: "var(--slate-600)", marginTop: 4 }}>{file.name}</div>}
          </FormField>
        </div>
        <Button
          variant="primary"
          onClick={submit}
          disabled={submitting || !instrument || !sourceDoc || !refPrefix || !file}
        >
          {submitting ? "Uploading…" : "Upload & extract clauses"}
        </Button>
      </Card>

      <Card>
        <h2 className="card__title">Documents</h2>
        {loadError ? (
          <EmptyState
            title="Couldn't load the Library"
            description={
              loadError.includes("Missing permission")
                ? "You don't have permission to view the Regulation Library. Switch to a Risk Manager or Administrator account."
                : loadError
            }
          />
        ) : documents.length === 0 ? (
          <EmptyState title="No regulation documents yet" description="Upload a PDF above to get started." />
        ) : (
          <DataTable>
            <thead>
              <tr>
                <th>Regulator</th>
                <th>Instrument</th>
                <th>Source document</th>
                <th>Status</th>
                <th>Clauses</th>
                <th>Uploaded</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((d) => (
                <tr key={d.id}>
                  <td><strong>{d.regulator}</strong></td>
                  <td>{d.instrument}</td>
                  <td>{d.source_doc}</td>
                  <td><Badge variant={STATUS_VARIANT[d.status]}>{STATUS_LABEL[d.status]}</Badge></td>
                  <td>{d.clause_count}</td>
                  <td>{new Date(d.created_at).toLocaleDateString()}</td>
                  <td style={{ display: "flex", gap: 8 }}>
                    {(d.status === "pending_review" || d.status === "active") && (
                      <Button size="sm" variant="secondary" onClick={() => openReview(d)}>
                        Review clauses
                      </Button>
                    )}
                    {d.status === "pending_review" && (
                      <Button size="sm" variant="primary" onClick={() => activate(d.id)}>
                        Activate
                      </Button>
                    )}
                    {d.status === "active" && (
                      <Button size="sm" variant="danger" onClick={() => archive(d.id)}>
                        Archive
                      </Button>
                    )}
                    {d.status === "archived" && (
                      <Button size="sm" variant="primary" onClick={() => activate(d.id)}>
                        Reactivate
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        )}
      </Card>

      {reviewing && (
        <>
          <div className="clause-viewer-backdrop" onClick={() => setReviewing(null)} aria-hidden="true" />
          <aside className="clause-viewer-panel" aria-label="Extracted clauses review" style={{ padding: 20, overflowY: "auto" }}>
            <h2 className="card__title">
              {reviewing.source_doc} — {reviewClauses.length} extracted clause{reviewClauses.length === 1 ? "" : "s"}
            </h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {reviewClauses.map((c) => (
                <div key={c.id} style={{ border: "1px solid var(--color-separator)", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontSize: 12, color: "var(--slate-500)", marginBottom: 4 }}>
                    {c.clause_ref} · p.{c.page_no}
                  </div>
                  <div style={{ fontSize: 14, whiteSpace: "pre-wrap" }}>{c.text}</div>
                </div>
              ))}
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
              {reviewing.status === "pending_review" && (
                <Button variant="primary" onClick={() => activate(reviewing.id)}>
                  Looks good — activate
                </Button>
              )}
              <Button variant="ghost" onClick={() => setReviewing(null)}>
                Close
              </Button>
            </div>
          </aside>
        </>
      )}
    </div>
  );
}
