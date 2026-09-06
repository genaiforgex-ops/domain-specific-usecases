import { useEffect, useMemo, useRef, useState } from "react";
import { Link, Route, Routes, useNavigate, useParams } from "react-router-dom";

import { DiffView, type DiffViewHandle } from "@/components/DiffView";
import { Icon } from "@/components/Icons";
import { UploadZone } from "@/components/UploadZone";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { Input } from "@/components/ui/Input";
import { api } from "@/lib/api";
import { formatDate, riskColor } from "@/lib/utils";
import type { Comparison, ComparisonSummary } from "@/types";

export function DocumentComparisonPage() {
  return (
    <Routes>
      <Route index element={<List />} />
      <Route path="new" element={<NewComparison />} />
      <Route path=":id" element={<Detail />} />
    </Routes>
  );
}

function HidableHelp({
  title,
  defaultOpen = false,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-lg border border-separator/40 bg-bg overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-left hover:bg-bg-secondary transition-colors"
        aria-expanded={open}
      >
        <span className="text-sm font-medium text-label">{title}</span>
        <span className="text-xs text-label-tertiary shrink-0">{open ? "Hide ▴" : "Show ▾"}</span>
      </button>
      {open && (
        <div className="px-4 pb-3 pt-0 border-t border-separator/30 text-sm text-label-secondary leading-relaxed">
          {children}
        </div>
      )}
    </div>
  );
}

function List() {
  const [rows, setRows] = useState<ComparisonSummary[]>([]);
  useEffect(() => {
    api.listComparisons().then(setRows);
  }, []);
  return (
    <div className="space-y-6 pb-10">
      <PageHeader
        title="Document Comparison"
        subtitle="Upload any two PDF, DOCX, or TXT files for a side-by-side diff with risk flags on material changes."
        actions={
          <Link to="new">
            <Button>
              <Icon.Plus className="w-4 h-4 mr-1.5" aria-hidden />
              New comparison
            </Button>
          </Link>
        }
      />
      <HidableHelp title="How to use · tips">
        <p className="mt-2">
          Upload Document A and Document B (contracts, policies, or redlines from outside LegalOS).
          On the result page, use ↑ / ↓ to jump between changes.
        </p>
        <p className="text-xs text-label-tertiary mt-2">
          MSA negotiation versions stay in{" "}
          <Link to="/msa-automation" className="text-accent hover:underline">
            MSA Automation
          </Link>
          — they are not listed here.
        </p>
      </HidableHelp>
      <Card title="Your comparisons">
        {rows.length === 0 ? (
          <div className="text-sm text-label-secondary">
            No standalone comparisons yet. Start with{" "}
            <Link to="new" className="text-accent hover:underline">
              New comparison
            </Link>{" "}
            and upload two files.
          </div>
        ) : (
          <ul className="divide-y divide-separator/30">
            {rows.map((r) => (
              <li key={r.id} className="py-2 flex justify-between items-center gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-label truncate">{r.label}</div>
                  <div className="text-xs text-label-secondary truncate">
                    {r.v1_filename} ↔ {r.v2_filename} · {formatDate(r.created_at)}
                  </div>
                </div>
                <Link to={`${r.id}`} className="text-sm text-accent hover:underline shrink-0">
                  Open →
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function NewComparison() {
  const navigate = useNavigate();
  const [label, setLabel] = useState("");
  const [fileA, setFileA] = useState<File | null>(null);
  const [fileB, setFileB] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!fileA || !fileB) {
      setError("Upload both Document A and Document B (PDF, DOCX, or TXT).");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("label", label.trim() || `${fileA.name} vs ${fileB.name}`);
      form.append("file_a", fileA);
      form.append("file_b", fileB);
      const comp = await api.createComparisonUpload(form);
      navigate(`../${comp.id}`);
    } catch (err) {
      setError((err as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-5xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-label">New comparison</h1>
        <p className="text-sm text-label-secondary mt-1">
          Upload two documents to compare. Text is extracted automatically from PDF, DOCX, or TXT.
        </p>
      </div>

      <HidableHelp title="Instructions">
        <ol className="list-decimal list-inside space-y-1.5 mt-2">
          <li>Give the comparison a short label (e.g. “Vendor NDA — April vs May”).</li>
          <li>
            Upload <strong className="font-medium text-label">Document A</strong> (baseline) and{" "}
            <strong className="font-medium text-label">Document B</strong> (later / counterparty).
          </li>
          <li>
            Formats: <strong className="font-medium text-label">PDF, DOCX, TXT</strong> (max 50 MB
            each).
          </li>
          <li>Compare — then use ↑ / ↓ on the result to jump between changes.</li>
        </ol>
        <p className="text-xs text-label-tertiary mt-3 border-t border-separator/40 pt-3">
          For MSA negotiation versions use{" "}
          <Link to="/msa-automation" className="text-accent hover:underline">
            MSA Automation
          </Link>
          .
        </p>
      </HidableHelp>

      <Card>
        <form className="space-y-5" onSubmit={submit}>
          <Input
            label="Comparison label"
            placeholder="e.g. NDA — our draft vs counterparty mark-up"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            required
          />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <div className="text-sm font-medium text-label">Document A</div>
              <p className="text-xs text-label-tertiary">Baseline / earlier draft</p>
              <UploadZone
                file={fileA}
                onFile={setFileA}
                disabled={submitting}
                label="Drop PDF, DOCX, or TXT here"
                hint="or click to browse — Document A"
              />
            </div>
            <div className="space-y-2">
              <div className="text-sm font-medium text-label">Document B</div>
              <p className="text-xs text-label-tertiary">Later / counterparty draft</p>
              <UploadZone
                file={fileB}
                onFile={setFileB}
                disabled={submitting}
                label="Drop PDF, DOCX, or TXT here"
                hint="or click to browse — Document B"
              />
            </div>
          </div>
          {error && <p className="text-sm text-error">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => navigate("..")}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting || !fileA || !fileB}>
              {submitting ? "Comparing…" : "Compare documents"}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}

function Detail() {
  const { id } = useParams<{ id: string }>();
  const [comp, setComp] = useState<Comparison | null>(null);
  const diffRef = useRef<DiffViewHandle>(null);
  const [jumpCursor, setJumpCursor] = useState(0);

  useEffect(() => {
    if (id) api.getComparison(Number(id)).then(setComp);
  }, [id]);

  const changeIndices = useMemo(
    () =>
      (comp?.diff_blocks ?? []).reduce<number[]>((acc, b, i) => {
        if (b.kind !== "equal") acc.push(i);
        return acc;
      }, []),
    [comp?.diff_blocks],
  );

  useEffect(() => {
    setJumpCursor(0);
  }, [comp?.id]);

  function jumpToChange(step: number) {
    if (changeIndices.length === 0) return;
    const next = (jumpCursor + step + changeIndices.length) % changeIndices.length;
    setJumpCursor(next);
    const index = changeIndices[next];
    window.setTimeout(() => diffRef.current?.scrollToIndex(index), 40);
  }

  if (!comp) return <div className="text-label-secondary text-sm">Loading…</div>;

  return (
    <div className="space-y-5">
      <Link to=".." className="text-sm text-accent hover:underline">
        ← Back
      </Link>
      <div>
        <h1 className="text-2xl font-semibold text-label">{comp.label}</h1>
        <p className="text-sm text-label-secondary mt-1">
          {comp.v1_filename} ↔ {comp.v2_filename}
        </p>
        <p className="text-sm text-label-secondary mt-1">{comp.summary_report}</p>
      </div>

      {comp.risk_commentary.length > 0 && (
        <Card title="Risk commentary on material changes" subtitle={`${comp.risk_commentary.length} flagged`}>
          <ul className="space-y-2">
            {comp.risk_commentary.map((r, i) => (
              <li key={i} className="border-l-4 border-amber-400 bg-amber-50 px-3 py-2 rounded">
                <div className="flex items-center gap-2 mb-1">
                  <Badge className={riskColor(r.severity)}>{r.severity}</Badge>
                </div>
                <div className="text-sm text-label-secondary italic">"{r.excerpt}"</div>
                <div className="text-sm text-label-secondary mt-1">{r.rationale}</div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card
        title="Side-by-side diff"
        subtitle={
          changeIndices.length === 0
            ? "No differences found"
            : `${changeIndices.length} change${changeIndices.length === 1 ? "" : "s"} — use ↑ / ↓ to jump`
        }
        actions={
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-label-secondary whitespace-nowrap tabular-nums">
              {changeIndices.length === 0
                ? "—"
                : `${Math.min(jumpCursor + 1, changeIndices.length)} / ${changeIndices.length}`}
            </span>
            <Button
              size="sm"
              variant="secondary"
              disabled={changeIndices.length === 0}
              onClick={() => jumpToChange(-1)}
              title="Previous change"
              aria-label="Previous change"
            >
              ↑
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={changeIndices.length === 0}
              onClick={() => jumpToChange(1)}
              title="Next change"
              aria-label="Next change"
            >
              ↓
            </Button>
          </div>
        }
      >
        <p className="text-xs text-label-tertiary mb-3">
          Jump between changes to review both documents in sync. Modified lines highlight the exact
          words that changed.
        </p>
        <DiffView
          ref={diffRef}
          v1Label={comp.v1_filename}
          v2Label={comp.v2_filename}
          blocks={comp.diff_blocks}
          height={560}
        />
      </Card>
    </div>
  );
}
