import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Document, Page, pdfjs } from "react-pdf";

import { OnlyOfficeEditor } from "@/components/OnlyOfficeEditor";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { classNames } from "@/lib/utils";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

const BASE = import.meta.env.VITE_API_URL || "";

const TEXT_LINES_PER_PAGE = 50;

export interface DocumentViewerHandle {
  /** Scroll the viewer to a page (1-indexed). */
  scrollToPage: (page: number) => void;
  /** Scroll to the first occurrence of `needle` and briefly highlight it. */
  scrollToText: (needle: string) => void;
}

type DocKind = "pdf" | "docx" | "text";

function detectKind(filename: string | null, mime: string | null | undefined): DocKind {
  const lc = (filename || "").toLowerCase();
  const m = (mime || "").toLowerCase();
  if (m.includes("pdf") || lc.endsWith(".pdf")) return "pdf";
  if (
    m.includes("officedocument.wordprocessingml") ||
    m.includes("msword") ||
    lc.endsWith(".docx") ||
    lc.endsWith(".doc")
  ) {
    return "docx";
  }
  return "text";
}

function paginateText(text: string): string[] {
  const lines = text.split("\n");
  const pages: string[] = [];
  for (let i = 0; i < lines.length; i += TEXT_LINES_PER_PAGE) {
    pages.push(lines.slice(i, i + TEXT_LINES_PER_PAGE).join("\n"));
  }
  return pages.length > 0 ? pages : [""];
}

/* ── Locating a source chunk inside a document ──────────────────────────────
 * A retrieved chunk is a single run of text, but the document it came from wraps
 * across lines, and PDF extraction inserts its own spacing. So neither the page
 * search nor the highlight can compare the two literally — both normalize
 * whitespace, and the highlight regex allows any whitespace between words.
 */

/** Collapse all whitespace runs to one space, lowercased, for comparison. */
function normalizeForMatch(s: string): string {
  return (s || "").replace(/\s+/g, " ").trim().toLowerCase();
}

/** A regex matching `needle` regardless of how the document wraps or spaces it. */
export function buildHighlightRegex(needle: string): RegExp | null {
  const words = normalizeForMatch(needle).split(" ").filter(Boolean);
  if (words.length === 0) return null;
  // Cap the pattern: a whole 4k chunk makes a regex that is slow and, because the
  // document rarely matches it end-to-end, matches nothing at all.
  const capped = words.slice(0, 24);
  const pattern = capped
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("\\s+");
  try {
    return new RegExp(`(${pattern})`, "gi");
  } catch {
    return null;
  }
}

/**
 * Progressively shorter word-runs from the start of a chunk.
 *
 * The first words of a retrieved chunk are the most reliable anchor, but clause
 * chunks repeat a parent heading and PDF extraction can mangle the odd word, so a
 * long probe that fails should fall back to a shorter one rather than give up.
 */
function matchProbes(needle: string): string[] {
  const words = normalizeForMatch(needle).split(" ").filter(Boolean);
  if (words.length === 0) return [];
  const probes: string[] = [];
  for (const n of [16, 10, 6, 4]) {
    if (words.length >= n) probes.push(words.slice(0, n).join(" "));
  }
  if (probes.length === 0) probes.push(words.join(" "));
  return [...new Set(probes)];
}

/** 1-based index of the first page whose text contains any probe, else null. */
function findPageByProbes(pages: string[], probes: string[]): number | null {
  const normalized = pages.map(normalizeForMatch);
  for (const probe of probes) {
    for (let i = 0; i < normalized.length; i++) {
      if (normalized[i].includes(probe)) return i + 1;
    }
  }
  return null;
}

export const DocumentViewer = forwardRef<
  DocumentViewerHandle,
  {
    storageKey: string | null;
    mimeType: string | null | undefined;
    filename: string | null;
    extractedText: string;
    title?: string;
    badge?: React.ReactNode;
    /** Page numbers (1-indexed) that contain a change — shown as markers in the scrollbar gutter. */
    changeMarkers?: Array<{ page: number; severity: string }>;
    /** When set for DOCX, render the document via ONLYOFFICE instead of mammoth fallback. */
    onlyofficeTrackerId?: number;
    onlyofficeVersionId?: number;
    /**
     * Override the binary fetch URL (e.g. template-library file endpoint).
     * Defaults to ``/api/msa/files/{storageKey}``.
     */
    fileUrl?: string | null;
  }
>(function DocumentViewer(
  {
    storageKey,
    mimeType,
    filename,
    extractedText,
    title,
    badge,
    changeMarkers,
    onlyofficeTrackerId,
    onlyofficeVersionId,
    fileUrl,
  },
  ref,
) {
  const kind = detectKind(filename, mimeType);
  const usePdf = kind === "pdf" && !!(fileUrl || storageKey);
  const useDocx = kind === "docx" && !!(fileUrl || storageKey);
  const useOnlyOffice = useDocx && !!onlyofficeTrackerId && !!onlyofficeVersionId;
  const resolvedFileUrl =
    fileUrl ||
    (storageKey ? `${BASE}/api/msa/files/${storageKey}` : null);

  const [pdfBlob, setPdfBlob] = useState<Blob | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [numPages, setNumPages] = useState<number>(0);
  const [scale, setScale] = useState<number>(1.0);
  const [query, setQuery] = useState<string>("");
  // The retrieved chunk to mark, kept apart from `query` so the search box is not
  // stuffed with a 4k excerpt. A typed query takes precedence when present.
  const [highlight, setHighlight] = useState<string>("");
  const [highlightPage, setHighlightPage] = useState<number | null>(null);
  const [docxHtml, setDocxHtml] = useState<string | null>(null);
  const [docxError, setDocxError] = useState<string | null>(null);
  const [ooConfig, setOoConfig] = useState<{ document_server_url: string; token: string; config?: Record<string, unknown> } | null>(null);
  const [ooError, setOoError] = useState<string | null>(null);
  const [docxPageCount, setDocxPageCount] = useState<number>(0);
  const [containerWidth, setContainerWidth] = useState<number>(700);
  const [fullscreen, setFullscreen] = useState(false);

  const scrollerRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Array<HTMLDivElement | null>>([]);
  const [visiblePage, setVisiblePage] = useState<number>(1);

  const textPages = useMemo(() => paginateText(extractedText), [extractedText]);
  const totalPages =
    usePdf ? numPages :
    useDocx ? docxPageCount :
    textPages.length;

  // Load PDF blob
  useEffect(() => {
    setPdfBlob(null);
    setPdfError(null);
    setNumPages(0);
    if (!usePdf || !resolvedFileUrl) return;
    let cancelled = false;
    fetch(resolvedFileUrl, { credentials: "include" })
      .then((r) => {
        if (!r.ok) throw new Error(`Failed (${r.status})`);
        return r.blob();
      })
      .then((b) => !cancelled && setPdfBlob(b))
      .catch((e) => !cancelled && setPdfError((e as Error).message));
    return () => {
      cancelled = true;
    };
  }, [resolvedFileUrl, usePdf]);

  // Fetch ONLYOFFICE config for DOCX workspace view.
  useEffect(() => {
    setOoConfig(null);
    setOoError(null);
    if (!useOnlyOffice || !onlyofficeTrackerId || !onlyofficeVersionId) return;
    let cancelled = false;
    api
      .getMSAOnlyOfficeConfig(onlyofficeTrackerId, onlyofficeVersionId, "view")
      .then((c) => {
        if (!cancelled) setOoConfig(c);
      })
      .catch((e) => {
        if (!cancelled) setOoError((e as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [useOnlyOffice, onlyofficeTrackerId, onlyofficeVersionId]);

  // Load + convert DOCX via mammoth fallback.
  useEffect(() => {
    setDocxHtml(null);
    setDocxError(null);
    setDocxPageCount(0);
    if (!useDocx || !resolvedFileUrl || useOnlyOffice) return;
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch(resolvedFileUrl, { credentials: "include" });
        if (!r.ok) throw new Error(`Failed (${r.status})`);
        const buf = await r.arrayBuffer();
        const mammoth = await import("mammoth");
        const { value } = await mammoth.convertToHtml({ arrayBuffer: buf });
        if (cancelled) return;
        // Split DOCX into pseudo-pages so we can show "Page X of Y" while scrolling.
        // We chunk by paragraph count (~30 paragraphs per page ≈ a printed page).
        const wrapper = document.createElement("div");
        wrapper.innerHTML = value;
        const blocks = Array.from(wrapper.children);
        const perPage = 30;
        const pages: string[] = [];
        for (let i = 0; i < blocks.length; i += perPage) {
          const slice = blocks.slice(i, i + perPage).map((n) => n.outerHTML).join("");
          pages.push(slice);
        }
        if (pages.length === 0) pages.push(value);
        setDocxHtml(JSON.stringify(pages));
        setDocxPageCount(pages.length);
      } catch (e) {
        if (!cancelled) setDocxError((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [resolvedFileUrl, useDocx, useOnlyOffice]);

  // Track container width for responsive PDF pages
  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = entry.contentRect.width - 32; // padding
        if (w > 100) setContainerWidth(w);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Observe which page is visible while scrolling
  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    const observer = new IntersectionObserver(
      (entries) => {
        // Find the entry with the largest visible area
        let best: { page: number; ratio: number } | null = null;
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          const p = Number((e.target as HTMLElement).dataset.page || 0);
          if (!p) continue;
          if (!best || e.intersectionRatio > best.ratio) {
            best = { page: p, ratio: e.intersectionRatio };
          }
        }
        if (best) setVisiblePage(best.page);
      },
      { root: scroller, threshold: [0.25, 0.5, 0.75] },
    );
    pageRefs.current.forEach((el) => {
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [numPages, docxPageCount, textPages.length, kind]);

  const scrollToPage = useCallback((page: number) => {
    const idx = Math.max(1, page) - 1;
    const el = pageRefs.current[idx];
    if (el && scrollerRef.current) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      el.classList.add("ring-2", "ring-accent");
      setTimeout(() => el.classList.remove("ring-2", "ring-accent"), 1800);
    }
  }, []);

  const scrollToText = useCallback(
    (needle: string) => {
      if (!needle || !needle.trim()) return;
      const probes = matchProbes(needle);
      if (probes.length === 0) return;

      // Highlight the whole chunk (whitespace-flexible), not just the probe, so the
      // reader sees the full sourced passage marked rather than its first few words.
      setHighlight(needle);
      setHighlightPage(null);

      // PDF: search the real text layer, which is what the reader is looking at.
      if (usePdf && pdfBlob) {
        void (async () => {
          try {
            const data = await pdfBlob.arrayBuffer();
            const pdf = await pdfjs.getDocument({ data: data.slice(0) }).promise;
            const pageTexts: string[] = [];
            for (let p = 1; p <= pdf.numPages; p++) {
              const page = await pdf.getPage(p);
              const content = await page.getTextContent();
              pageTexts.push(
                content.items.map((it) => ("str" in it ? String(it.str) : "")).join(" "),
              );
            }
            const found = findPageByProbes(pageTexts, probes);
            if (found) {
              // Scope PDF marking to this page: the same wording can recur elsewhere.
              setHighlightPage(found);
              scrollToPage(found);
              return;
            }
          } catch {
            /* fall through to extracted-text pages */
          }
          const fallback = findPageByProbes(textPages, probes);
          if (fallback) {
            setHighlightPage(fallback);
            scrollToPage(fallback);
          }
        })();
        return;
      }

      const found = findPageByProbes(textPages, probes);
      if (found) {
        setHighlightPage(found);
        scrollToPage(found);
      }
    },
    [textPages, scrollToPage, usePdf, pdfBlob],
  );

  useImperativeHandle(ref, () => ({ scrollToPage, scrollToText }), [scrollToPage, scrollToText]);

  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFullscreen(false);
    };
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    // Remeasure after layout so PDF/OnlyOffice fill the viewport.
    window.setTimeout(() => window.dispatchEvent(new Event("resize")), 50);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [fullscreen]);

  function renderTextWithHighlights(s: string): React.ReactNode {
    // A typed search wins; otherwise mark the chunk the citation pointed at.
    const q = query.trim() || highlight;
    if (!q) return s;
    const re = buildHighlightRegex(q);
    if (!re) return s;
    try {
      const parts = s.split(re);
      return parts.map((p, i) =>
        i % 2 === 1 ? (
          <mark key={i} className="bg-yellow-200 text-label">
            {p}
          </mark>
        ) : (
          <span key={i}>{p}</span>
        ),
      );
    } catch {
      return s;
    }
  }

  /**
   * Mark the sourced passage inside a PDF's text layer.
   *
   * pdf.js hands us one text item at a time, so a phrase spanning items cannot be
   * matched as a whole. Instead each item is marked when its own text sits inside
   * the chunk — which lights up the passage line by line. Short items are skipped:
   * a fragment like "the" occurs in nearly every chunk and would mark the page at
   * random, which is worse than no highlight.
   */
  const pdfTextRenderer = useMemo(() => {
    const active = query.trim() || highlight;
    const target = normalizeForMatch(active);
    if (!target) return undefined;
    return (item: { str: string; pageNumber?: number }) => {
      const raw = item.str ?? "";
      const escaped = raw.replace(/[&<>]/g, (c) =>
        c === "&" ? "&amp;" : c === "<" ? "&lt;" : "&gt;",
      );
      if (highlightPage && item.pageNumber && item.pageNumber !== highlightPage) {
        return escaped;
      }
      const piece = normalizeForMatch(raw);
      if (piece.length < 12 || !target.includes(piece)) return escaped;
      return `<mark class="pdf-chunk-hl">${escaped}</mark>`;
    };
  }, [query, highlight, highlightPage]);

  const docxPages: string[] = useMemo(() => {
    if (!docxHtml) return [];
    try {
      return JSON.parse(docxHtml);
    } catch {
      return [];
    }
  }, [docxHtml]);

  const shell = (
    <div
      className={classNames(
        "bg-bg flex flex-col overflow-hidden",
        fullscreen
          ? "h-full w-full min-h-0 rounded-none border-0"
          : "h-full border border-separator/40 rounded-lg",
      )}
    >
      <div className="px-3 py-2 border-b border-separator/30 flex items-center gap-2 bg-bg-secondary flex-shrink-0">
        {badge}
        <div className="flex-1 min-w-0">
          <div className="text-xs font-medium text-label-secondary truncate">
            {title || filename || "Document"}
          </div>
          <div className="text-[11px] text-label-secondary flex items-center gap-1">
            <span className="uppercase">{kind}</span>
            <span>·</span>
            <span>
              Page <span className="font-semibold text-label-secondary">{visiblePage}</span> /{" "}
              {totalPages || "—"}
            </span>
          </div>
        </div>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search…"
          className="w-32 text-xs px-2 py-1 border border-separator/60 rounded focus:outline-none focus:ring-1 focus:ring-accent"
        />
        {usePdf && (
          <>
            <button
              type="button"
              className="text-xs px-2 py-1 border border-separator/60 rounded hover:bg-bg-secondary"
              onClick={() => setScale((s) => Math.max(0.5, s - 0.15))}
              title="Zoom out"
            >
              −
            </button>
            <span className="text-xs text-label-secondary w-10 text-center">
              {Math.round(scale * 100)}%
            </span>
            <button
              type="button"
              className="text-xs px-2 py-1 border border-separator/60 rounded hover:bg-bg-secondary"
              onClick={() => setScale((s) => Math.min(2.5, s + 0.15))}
              title="Zoom in"
            >
              +
            </button>
          </>
        )}
        <Button
          size="sm"
          variant="secondary"
          onClick={() => {
            const v = Math.max(1, visiblePage - 1);
            scrollToPage(v);
          }}
          title="Previous page"
        >
          ↑
        </Button>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => scrollToPage(Math.min(totalPages, visiblePage + 1))}
          title="Next page"
        >
          ↓
        </Button>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => setFullscreen((v) => !v)}
          title={fullscreen ? "Exit fullscreen (Esc)" : "Open document fullscreen"}
        >
          {fullscreen ? "Exit" : "⛶"}
        </Button>
      </div>

      <div className="flex-1 flex min-h-0 relative">
        <div
          ref={scrollerRef}
          className="flex-1 overflow-auto bg-bg-secondary scroll-smooth"
        >
          {usePdf ? (
            pdfError ? (
              <div className="p-6 text-sm text-error">PDF failed to load: {pdfError}</div>
            ) : !pdfBlob ? (
              <div className="p-6 text-sm text-label-secondary">Loading PDF…</div>
            ) : (
              <Document
                file={pdfBlob}
                onLoadSuccess={({ numPages: n }) => {
                  setNumPages(n);
                  pageRefs.current = Array(n).fill(null);
                }}
                onLoadError={(e) => setPdfError(e.message)}
                loading={<div className="p-6 text-sm text-label-secondary">Rendering…</div>}
              >
                <div className="flex flex-col items-center gap-3 py-4">
                  {Array.from({ length: numPages }, (_, i) => i + 1).map((p) => (
                    <div
                      key={p}
                      ref={(el) => {
                        pageRefs.current[p - 1] = el;
                      }}
                      data-page={p}
                      className="relative shadow-md transition"
                    >
                      <div className="absolute -left-9 top-2 text-[10px] font-mono text-label-tertiary select-none">
                        {p}
                      </div>
                      <Page
                        pageNumber={p}
                        scale={scale}
                        width={containerWidth}
                        renderTextLayer
                        renderAnnotationLayer={false}
                        customTextRenderer={pdfTextRenderer}
                      />
                    </div>
                  ))}
                </div>
              </Document>
            )
          ) : useDocx ? (
            useOnlyOffice ? (
              ooError ? (
                <div className="p-6 text-sm text-amber-700">
                  ONLYOFFICE preview unavailable ({ooError}). Falling back to DOCX extract.
                </div>
              ) : !ooConfig ? (
                <div className="p-6 text-sm text-label-secondary">Loading document preview…</div>
              ) : (
                <OnlyOfficeEditor
                  documentServerUrl={ooConfig.document_server_url}
                  token={ooConfig.token}
                  config={ooConfig.config}
                  mode="view"
                  className="h-full border-0"
                />
              )
            ) : docxError ? (
              <div className="p-6 text-sm text-error">DOCX failed to load: {docxError}</div>
            ) : !docxHtml ? (
              <div className="p-6 text-sm text-label-secondary">Loading DOCX…</div>
            ) : (
              <div className="flex flex-col items-center gap-4 py-4 px-4">
                {docxPages.map((html, i) => (
                  <div
                    key={i}
                    ref={(el) => {
                      pageRefs.current[i] = el;
                    }}
                    data-page={i + 1}
                    className="relative bg-bg shadow-md w-full max-w-3xl px-10 py-12 transition rounded-sm"
                  >
                    <div className="absolute -left-9 top-2 text-[10px] font-mono text-label-tertiary select-none">
                      {i + 1}
                    </div>
                    <article
                      className="prose prose-sm max-w-none text-label docx-content"
                      dangerouslySetInnerHTML={{ __html: html }}
                    />
                    <div className="text-[10px] text-label-tertiary text-center mt-6 pt-4 border-t border-separator/30">
                      — Page {i + 1} of {docxPages.length} —
                    </div>
                  </div>
                ))}
              </div>
            )
          ) : (
            <div className="flex flex-col items-center gap-4 py-4 px-4">
              {textPages.map((page, i) => (
                <div
                  key={i}
                  ref={(el) => {
                    pageRefs.current[i] = el;
                  }}
                  data-page={i + 1}
                  className="relative bg-bg shadow-md w-full max-w-3xl px-10 py-10 transition rounded-sm"
                >
                  <div className="absolute -left-9 top-2 text-[10px] font-mono text-label-tertiary select-none">
                    {i + 1}
                  </div>
                  <pre className="text-xs font-mono whitespace-pre-wrap leading-relaxed text-label">
                    {renderTextWithHighlights(page)}
                  </pre>
                  <div className="text-[10px] text-label-tertiary text-center mt-6 pt-4 border-t border-separator/30">
                    — Page {i + 1} of {textPages.length} —
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Scrollbar-side change-marker gutter */}
        {changeMarkers && changeMarkers.length > 0 && totalPages > 0 && (
          <div className="w-3 bg-bg-secondary border-l border-separator/40 relative flex-shrink-0">
            {changeMarkers.map((m, i) => (
              <button
                key={i}
                type="button"
                onClick={() => scrollToPage(m.page)}
                title={`Change on page ${m.page} (${m.severity})`}
                className={classNames(
                  "absolute left-0 right-0 h-1.5 hover:h-2 transition-all",
                  m.severity.toLowerCase() === "high"
                    ? "bg-red-500"
                    : m.severity.toLowerCase() === "medium"
                      ? "bg-amber-500"
                      : "bg-blue-500",
                )}
                style={{ top: `${((m.page - 1) / totalPages) * 100}%` }}
              />
            ))}
          </div>
        )}
      </div>

      {/* Footer with page jump input */}
      <div className="px-3 py-1.5 border-t border-separator/30 flex items-center justify-between bg-bg-secondary flex-shrink-0 text-xs">
        <span className="text-label-secondary">
          {kind === "pdf" ? "Scroll to navigate · Ctrl+wheel to zoom" : "Scroll to navigate"}
        </span>
        <div className="flex items-center gap-1.5">
          <span className="text-label-secondary">Go to</span>
          <input
            type="number"
            value={visiblePage}
            min={1}
            max={Math.max(1, totalPages)}
            onChange={(e) => {
              const p = Number(e.target.value);
              if (p >= 1 && p <= totalPages) scrollToPage(p);
            }}
            className="w-12 text-center px-1.5 py-0.5 border border-separator/60 rounded"
          />
          <span className="text-label-secondary">/ {totalPages || "—"}</span>
        </div>
      </div>
    </div>
  );

  if (fullscreen) {
    return createPortal(
      <div className="fixed inset-0 z-[100] h-[100dvh] w-screen max-w-none flex flex-col bg-bg m-0 p-0 overflow-hidden">
        {shell}
      </div>,
      document.body,
    );
  }

  return shell;
});

export function DocumentViewerEmpty({ label }: { label: string }) {
  return (
    <div
      className="border border-dashed border-separator/60 rounded-lg bg-bg-secondary flex items-center justify-center text-sm text-label-secondary h-full"
      style={{ minHeight: 400 }}
    >
      {label}
    </div>
  );
}

/**
 * Given the extracted text of a document and a set of diff items,
 * estimate the page number each item lives on. Used to render change markers
 * in the scrollbar gutter and "Page N" badges in the change list.
 */
export function computeChangePages(
  extractedText: string,
  diffItems: Array<{ diff_index: number; old_text: string; new_text: string; severity: string }>,
  pageLineSize: number = TEXT_LINES_PER_PAGE,
): Map<number, { page: number; line: number; severity: string }> {
  const map = new Map<number, { page: number; line: number; severity: string }>();
  if (!extractedText) return map;
  const lower = extractedText.toLowerCase();
  for (const it of diffItems) {
    const probe = (it.new_text || it.old_text || "").trim().slice(0, 60).toLowerCase();
    if (!probe) continue;
    const off = lower.indexOf(probe);
    if (off < 0) continue;
    const lineNumber = extractedText.slice(0, off).split("\n").length;
    const page = Math.max(1, Math.ceil(lineNumber / pageLineSize));
    map.set(it.diff_index, { page, line: lineNumber, severity: it.severity });
  }
  return map;
}
