import { useEffect, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";
import { FETCH_CREDENTIALS } from "../api/client";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

export interface ClauseViewerTarget {
  regulator: string;
  instrument?: string | null;
  source_doc?: string | null;
  page_no?: number | null;
  para_no?: string | null;
  clause_id?: string | null;   // UUID — used for exact annotation lookup
  clause_ref?: string | null;
  clause_text?: string | null;
}

interface Props {
  target: ClauseViewerTarget | null;
  onClose: () => void;
}

export function ClauseViewerPanel({ target, onClose }: Props) {
  const [numPages, setNumPages] = useState<number>(0);
  const [pdfBlob, setPdfBlob] = useState<Blob | null>(null);
  const [pdfError, setPdfError] = useState(false);
  const [pageWidth] = useState<number>(500);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // Re-fetch annotated PDF whenever the cited clause changes
  useEffect(() => {
    setPdfBlob(null);
    setPdfError(false);
    setNumPages(0);

    const { regulator, instrument, clause_id } = target ?? {};
    if (!regulator || !instrument || !clause_id) return;

    const url = `/api/v1/clauses/pdf/annotated?regulator=${encodeURIComponent(regulator)}&instrument=${encodeURIComponent(instrument)}&clause_id=${encodeURIComponent(clause_id)}`;

    // credentials: the session is an httpOnly cookie, so this raw fetch must
    // opt in explicitly the same way api/client.ts does.
    fetch(url, { credentials: FETCH_CREDENTIALS })
      .then((r) => { if (!r.ok) throw new Error(`${r.status}`); return r.blob(); })
      .then(setPdfBlob)
      .catch(() => setPdfError(true));
  }, [target?.regulator, target?.instrument, target?.clause_id]);

  if (!target) return null;

  const { regulator, source_doc, page_no, para_no, clause_ref } = target;
  const title = source_doc ?? `${regulator}${target.instrument ? ` ${target.instrument}` : ""}`;
  const locator = [
    page_no ? `p.${page_no}` : null,
    para_no ? `Para ${para_no}` : null,
  ].filter(Boolean).join(" · ");

  // Render target page + one before and after for context
  const pagesToRender = pdfBlob && numPages > 0
    ? Array.from(new Set([
        Math.max(1, (page_no ?? 1) - 1),
        page_no ?? 1,
        Math.min(numPages, (page_no ?? 1) + 1),
      ])).filter((p) => p >= 1 && p <= numPages)
    : [];

  return (
    <>
      <div className="clause-viewer-backdrop" onClick={onClose} aria-hidden="true" />
      <aside className="clause-viewer-panel" aria-label="Source regulation viewer">
        <header className="clause-viewer__header">
          <div className="clause-viewer__header-text">
            <span className="clause-viewer__regulator-badge">{regulator}</span>
            <p className="clause-viewer__title">{title}</p>
            {locator && <p className="clause-viewer__locator">{locator}</p>}
            {clause_ref && <code className="clause-viewer__ref">{clause_ref}</code>}
          </div>
          <button className="clause-viewer__close" onClick={onClose} aria-label="Close panel">✕</button>
        </header>

        <div className="clause-viewer__body">
          {pdfError && (
            <div className="clause-viewer__no-pdf">
              PDF not available yet.<br />Drop it in resources/regulations/ and re-ingest.
            </div>
          )}
          {!pdfError && !pdfBlob && (
            <div className="clause-viewer__loading">Annotating PDF…</div>
          )}
          {pdfBlob && (
            <Document
              file={pdfBlob}
              onLoadSuccess={({ numPages: n }) => {
                setNumPages(n);
                setTimeout(() => {
                  document.getElementById(`pdf-page-${page_no ?? 1}`)
                    ?.scrollIntoView({ behavior: "smooth", block: "start" });
                }, 150);
              }}
              loading={<div className="clause-viewer__loading">Rendering…</div>}
              error={<div className="clause-viewer__no-pdf">Failed to render PDF.</div>}
            >
              {pagesToRender.map((p) => (
                <div
                  key={p}
                  id={`pdf-page-${p}`}
                  className={`clause-viewer__page-wrap${p === (page_no ?? 1) ? " clause-viewer__page-wrap--active" : ""}`}
                >
                  <span className="clause-viewer__page-label">Page {p}</span>
                  <Page
                    pageNumber={p}
                    width={pageWidth}
                    renderAnnotationLayer={false}
                  />
                </div>
              ))}
            </Document>
          )}
        </div>
      </aside>
    </>
  );
}
