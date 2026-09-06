import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { PageHeader } from "@/components/ui/PageHeader";
import { Select } from "@/components/ui/Select";
import { api } from "@/lib/api";
import { classNames, formatDate } from "@/lib/utils";
import type { CorpusChunk, CorpusDoc, CorpusOverview } from "@/types";

const DOMAIN_LABELS: Record<string, string> = {
  payments_banking: "Payments & Banking",
  lending_credit: "Lending & Credit",
  investments_wealth: "Investments & Wealth",
  insurance: "Insurance",
  data_privacy_cyber: "Data Privacy & Cyber",
  aml_kyc: "AML & KYC",
  consumer_protection: "Consumer Protection",
};

const STATUS_STYLES: Record<string, string> = {
  ingested: "border-success/40 bg-success/10 text-success",
  stale: "border-warning/40 bg-warning/10 text-warning",
  failed: "border-danger/40 bg-danger/10 text-danger",
  missing: "border-separator/45 bg-bg-secondary/60 text-label-tertiary",
};

const STATUS_TEXT: Record<string, string> = {
  ingested: "Ingested",
  stale: "Needs re-download",
  failed: "Failed",
  missing: "Not ingested",
};

function StatusBadge({ doc }: { doc: CorpusDoc }) {
  return (
    <Badge className={STATUS_STYLES[doc.status] ?? STATUS_STYLES.missing}>
      {STATUS_TEXT[doc.status] ?? doc.status}
    </Badge>
  );
}

/** One manifest row: metadata, ingest state, and the upload / inspect actions. */
function DocRow({
  doc,
  onChanged,
  onError,
}: {
  doc: CorpusDoc;
  onChanged: (message: string) => void;
  onError: (message: string) => void;
}) {
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [chunks, setChunks] = useState<CorpusChunk[] | null>(null);

  async function upload(file: File) {
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await api.uploadCorpusDocument(doc.doc_id, form, true);
      onChanged(
        res.skipped
          ? `${doc.doc_id}: ${res.message}`
          : `${doc.doc_id}: ingested ${res.chunk_count} clauses from ${res.page_count} page(s).`,
      );
    } catch (err) {
      onError(`${doc.doc_id}: ${(err as Error).message}`);
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function autoFetch() {
    setBusy(true);
    try {
      const res = await api.fetchCorpusDocument(doc.doc_id, true);
      onChanged(`${doc.doc_id}: ingested ${res.chunk_count} clauses from the official URL.`);
    } catch (err) {
      onError(`${doc.doc_id}: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function toggleChunks() {
    if (chunks) {
      setChunks(null);
      return;
    }
    try {
      setChunks(await api.corpusChunks(doc.doc_id, 40));
    } catch (err) {
      onError(`${doc.doc_id}: ${(err as Error).message}`);
    }
  }

  async function remove() {
    if (!window.confirm(`Remove ${doc.doc_id} and all its clause chunks from the corpus?`)) {
      return;
    }
    setBusy(true);
    try {
      await api.deleteCorpusDocument(doc.doc_id);
      onChanged(`${doc.doc_id}: removed from the corpus.`);
    } catch (err) {
      onError(`${doc.doc_id}: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  const ingested = doc.status === "ingested" || doc.status === "stale";

  return (
    <div className="border-b border-separator/50 px-4 py-3 last:border-b-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-caption text-label-tertiary">{doc.doc_id}</span>
            <Badge className="border-accent/30 bg-accent/10 text-accent">{doc.priority}</Badge>
            <StatusBadge doc={doc} />
            {doc.superseded_by ? (
              <Badge className="border-warning/40 bg-warning/10 text-warning">
                superseded by {doc.superseded_by}
              </Badge>
            ) : null}
          </div>
          <div className="mt-1 text-subhead font-medium text-label">{doc.title}</div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-caption text-label-tertiary">
            <span>{doc.issuer}</span>
            <span>{doc.doc_type.replace(/_/g, " ")}</span>
            <span>
              {doc.version_or_effective === "check-latest"
                ? "updated in place"
                : doc.effective_date
                  ? `effective ${doc.effective_date}`
                  : doc.version_or_effective}
            </span>
            {ingested ? (
              <span className="text-label-secondary">
                {doc.chunk_count} clauses · {doc.page_count} pages
                {doc.ingested_at ? ` · ${formatDate(doc.ingested_at)}` : ""}
              </span>
            ) : null}
            {doc.official_url ? (
              <a
                href={doc.official_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent hover:underline"
              >
                official source ↗
              </a>
            ) : null}
          </div>
          {doc.last_error ? (
            <div className="mt-1 text-caption text-danger">{doc.last_error}</div>
          ) : null}
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.doc,.txt,.html,.htm"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void upload(file);
            }}
          />
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => fileRef.current?.click()}
          >
            {busy ? "Working…" : ingested ? "Re-upload" : "Upload"}
          </Button>
          {doc.can_auto_fetch ? (
            <Button variant="ghost" disabled={busy} onClick={() => void autoFetch()}>
              Fetch
            </Button>
          ) : null}
          {ingested ? (
            <Button variant="ghost" onClick={() => void toggleChunks()}>
              {chunks ? "Hide clauses" : "Clauses"}
            </Button>
          ) : null}
          {ingested ? (
            <Button variant="ghost" disabled={busy} onClick={() => void remove()}>
              Remove
            </Button>
          ) : null}
        </div>
      </div>

      {chunks ? (
        <div className="mt-3 max-h-80 overflow-y-auto rounded-lg border border-separator/60 bg-bg-secondary/50">
          {chunks.length === 0 ? (
            <div className="px-3 py-2 text-caption text-label-tertiary">No clauses stored.</div>
          ) : (
            chunks.map((c) => (
              <div key={c.chunk_key} className="border-b border-separator/40 px-3 py-2 last:border-b-0">
                <div className="flex flex-wrap items-center gap-2 text-caption">
                  <span className="rounded bg-accent/10 px-1.5 py-0.5 font-medium text-accent">
                    {c.section_label ?? `chunk ${c.ordinal}`}
                  </span>
                  {c.parent_heading ? (
                    <span className="text-label-tertiary">{c.parent_heading}</span>
                  ) : null}
                  <span className="text-label-tertiary">
                    p{c.page} · {c.token_count} tokens
                  </span>
                </div>
                <p className="mt-1 whitespace-pre-wrap text-caption leading-relaxed text-label-secondary">
                  {c.text.slice(0, 400)}
                  {c.text.length > 400 ? "…" : ""}
                </p>
              </div>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
}

export function RegulatoryCorpusPage() {
  const [overview, setOverview] = useState<CorpusOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [banner, setBanner] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [domain, setDomain] = useState<string>("all");
  const [status, setStatus] = useState<string>("all");
  const [q, setQ] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setOverview(await api.corpusOverview());
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onChanged = useCallback(
    (message: string) => {
      setBanner(message);
      setError(null);
      void load();
    },
    [load],
  );

  const documents = overview?.documents ?? [];
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return documents.filter((d) => {
      if (domain !== "all" && d.domain !== domain) return false;
      if (status !== "all" && d.status !== status) return false;
      if (!needle) return true;
      return (
        d.title.toLowerCase().includes(needle) ||
        d.doc_id.toLowerCase().includes(needle) ||
        d.issuer.toLowerCase().includes(needle) ||
        d.tags.some((t) => t.includes(needle))
      );
    });
  }, [documents, domain, status, q]);

  const grouped = useMemo(() => {
    const out = new Map<string, CorpusDoc[]>();
    for (const doc of filtered) {
      const list = out.get(doc.domain) ?? [];
      list.push(doc);
      out.set(doc.domain, list);
    }
    return [...out.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [filtered]);

  const totals = overview?.totals;
  const staleCount = useMemo(
    () => documents.filter((d) => d.status === "stale").length,
    [documents],
  );

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Knowledge"
        title="Regulatory Corpus"
        subtitle="The law LawGenie cites. Download each instrument from its official source and upload it here — it is split into clauses so answers can cite the exact provision. Filter by “Needs re-download” when documents go stale."
        actions={
          <>
            <Button variant="ghost" onClick={() => void load()} disabled={loading}>
              {loading ? "Loading…" : "Refresh"}
            </Button>
            <Button
              variant="secondary"
              onClick={async () => {
                try {
                  const res = await api.refreshCorpusSupersession();
                  onChanged(`Resolved ${res.reindexed} supersession link(s).`);
                } catch (err) {
                  setError((err as Error).message);
                }
              }}
            >
              Re-check supersession
            </Button>
          </>
        }
      />

      {totals ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Card className="p-4">
            <div className="text-caption uppercase tracking-wide text-label-tertiary">Ingested</div>
            <div className="mt-1 font-display text-title-2 text-label">
              {totals.ingested}{" "}
              <span className="text-body text-label-tertiary">of {totals.manifest_total}</span>
            </div>
          </Card>
          <Card className="p-4">
            <div className="text-caption uppercase tracking-wide text-label-tertiary">
              Citable clauses
            </div>
            <div className="mt-1 font-display text-title-2 text-label">{totals.chunks}</div>
          </Card>
          <Card className="p-4">
            <div className="text-caption uppercase tracking-wide text-label-tertiary">
              Still to load
            </div>
            <div className="mt-1 font-display text-title-2 text-label">
              {totals.manifest_total - totals.ingested}
            </div>
          </Card>
        </div>
      ) : null}

      {banner ? (
        <div className="rounded-lg border border-success/40 bg-success/10 px-3 py-2 text-footnote text-success">
          {banner}
        </div>
      ) : null}
      {error ? (
        <div className="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-footnote text-danger">
          {error}
        </div>
      ) : null}
      {staleCount > 0 ? (
        <div className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-footnote text-warning">
          {staleCount} document{staleCount === 1 ? "" : "s"} need re-download (status: stale).
          Filter by “Needs re-download”, upload the latest official PDF/HTML, then re-ingest so
          LawGenie Research cites current law.
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Search title, doc id, issuer or tag…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="max-w-xs"
        />
        <Select value={domain} onChange={(e) => setDomain(e.target.value)}>
          <option value="all">All domains</option>
          {Object.entries(DOMAIN_LABELS).map(([id, label]) => (
            <option key={id} value={id}>
              {label}
            </option>
          ))}
        </Select>
        <Select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="all">All statuses</option>
          <option value="missing">Not ingested</option>
          <option value="ingested">Ingested</option>
          <option value="stale">Needs re-download</option>
          <option value="failed">Failed</option>
        </Select>
        <span className="text-caption text-label-tertiary">
          {filtered.length} of {documents.length} documents
        </span>
      </div>

      {grouped.map(([domainId, docs]) => (
        <Card key={domainId} className="overflow-hidden p-0">
          <div className="flex items-center justify-between border-b border-separator/60 bg-bg-secondary/40 px-4 py-2">
            <span className="text-subhead font-semibold text-label">
              {DOMAIN_LABELS[domainId] ?? domainId}
            </span>
            <span className="text-caption text-label-tertiary">
              {docs.filter((d) => d.status === "ingested").length}/{docs.length} ingested
            </span>
          </div>
          {docs.map((doc) => (
            <DocRow key={doc.doc_id} doc={doc} onChanged={onChanged} onError={setError} />
          ))}
        </Card>
      ))}

      {!loading && filtered.length === 0 ? (
        <Card className="p-6 text-center text-footnote text-label-tertiary">
          No documents match these filters.
        </Card>
      ) : null}

      <p className={classNames("text-caption text-label-tertiary")}>
        Bulk loading: drop files named by doc_id (e.g. <code>LEND-DLD-2025.pdf</code>) into the
        staging folder and run <code>python backend/scripts/sync_regulatory_to_rag.py</code>.
      </p>
    </div>
  );
}
