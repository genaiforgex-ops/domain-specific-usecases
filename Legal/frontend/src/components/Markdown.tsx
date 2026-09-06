import { useEffect, useId, useMemo, useState, type ReactNode } from "react";
import ReactMarkdown, { defaultUrlTransform, type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import type { ChatSource } from "@/types";
import { normalizeMarkdownTables } from "@/lib/markdownTables";

/**
 * Renders assistant messages as rich Markdown (GitHub-flavored: tables,
 * task lists, strikethrough). Raw HTML is NOT rendered (react-markdown's safe
 * default), so untrusted model output can't inject markup. Styling lives in the
 * `.md-body` block in index.css so it stays theme-aware.
 *
 * When ``sources`` is provided, ``[n]`` citation markers and common source
 * labels (``[JFPSL template]``, ``[attached document]``, …) become clickable
 * chips and call ``onOpenSource``. http(s) links open in a new tab; ``gs://``
 * is never opened as a browser tab.
 */
/**
 * Keep our internal citation schemes intact.
 *
 * react-markdown's default transform allows only http/https/mailto/tel and blanks
 * everything else, so `legalos://source/12` became `href=""` — and an anchor with
 * an empty href reloads the current URL, which remounts the SPA and looks like
 * "clicking a citation starts a new chat". These two schemes never reach the
 * browser: the `a` renderer turns them into buttons.
 */
function citationUrlTransform(url: string): string {
  if (/^(legalos|gs):\/\//i.test(url)) return url;
  return defaultUrlTransform(url);
}

const UNVERIFIED_TITLE =
  "Citation could not be verified against the source excerpt";

export function Markdown({
  text,
  sources,
  onOpenSource,
}: {
  text: string;
  sources?: ChatSource[];
  onOpenSource?: (index: number) => void;
}) {
  const sourceCount = sources?.length ?? 0;
  const prepared = useMemo(() => {
    const withTables = normalizeMarkdownTables(text);
    return linkifyCitations(withTables, sources ?? []);
  }, [text, sources]);

  const components: Components = {
    a: ({ href, children, ...props }) => {
      const h = href || "";

      if (h === "legalos://unverified") {
        return (
          <span
            className="cite-chip cite-chip--unverified"
            title={UNVERIFIED_TITLE}
          >
            unverified
          </span>
        );
      }

      if (h.startsWith("#ref-") || h.startsWith("legalos://source/")) {
        const raw = h.startsWith("#ref-")
          ? h.slice("#ref-".length)
          : h.slice("legalos://source/".length);
        const n = Number(raw);
        if (Number.isFinite(n) && n >= 1) {
          const src = sources?.[n - 1];
          const label = citationLabel(src, n);
          return (
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onOpenSource?.(n - 1);
              }}
              className="cite-chip"
              title={
                src?.section_label
                  ? fullCitation(src)
                  : src?.page
                    ? `Jump to page ${src.page}${src.title ? ` — ${src.title}` : ""}`
                    : src?.title || `Open source ${n}`
              }
            >
              {label}
            </button>
          );
        }
      }

      if (/^https?:\/\//i.test(h)) {
        return (
          <a {...props} href={h} target="_blank" rel="noopener noreferrer">
            {children}
          </a>
        );
      }

      if (/^gs:\/\//i.test(h)) {
        return (
          <button
            type="button"
            className="cite-chip"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              const idx = sources?.findIndex(
                (s) =>
                  s.url === h ||
                  (s.storage_key && h.endsWith(s.storage_key)) ||
                  s.title === String(childrenToText(children)),
              );
              if (idx != null && idx >= 0) onOpenSource?.(idx);
            }}
          >
            {children}
          </button>
        );
      }

      // No usable target (e.g. a scheme the transform blanked): render inert text
      // rather than an <a href="">, which would reload the app on click.
      if (!h) {
        return <span {...props}>{children}</span>;
      }

      return (
        <a {...props} href={h}>
          {children}
        </a>
      );
    },
    img: ({ src, alt }) => {
      const url = typeof src === "string" ? src : "";
      if (!/^https:\/\//i.test(url)) {
        return (
          <span className="text-xs text-label-tertiary italic">
            [image omitted — https only]
          </span>
        );
      }
      return (
        <a href={url} target="_blank" rel="noopener noreferrer" className="block">
          <img src={url} alt={alt || "Illustration"} loading="lazy" referrerPolicy="no-referrer" />
        </a>
      );
    },
    // Unwrap default <pre> so block code / Mermaid own their container.
    pre: ({ children }) => <>{children}</>,
    table: ({ children }) => (
      <div className="md-table-wrap">
        <table>{children}</table>
      </div>
    ),
    code: ({ className, children, ...props }) => {
      const match = /language-(\w+)/.exec(className || "");
      const lang = match?.[1]?.toLowerCase();
      const raw = String(childrenToText(children)).replace(/\n$/, "");

      if (lang === "mermaid") {
        return <MermaidBlock chart={raw} />;
      }

      if (lang || raw.includes("\n")) {
        return (
          <pre>
            <code className={className} {...props}>
              {children}
            </code>
          </pre>
        );
      }

      return (
        <code className={className} {...props}>
          {children}
        </code>
      );
    },
  };

  return (
    <div className="md-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={components}
        urlTransform={citationUrlTransform}
      >
        {prepared}
      </ReactMarkdown>
      {/* Fallback: if markdown ate the links, still show a clickable cite strip */}
      {sourceCount > 0 && !prepared.includes("legalos://source/") && hasBareCitations(text) && (
        <div className="cite-fallback mt-2 flex flex-wrap gap-1.5">
          {sources!.map((s, i) => (
            <button
              key={s.chunk_id || i}
              type="button"
              className="cite-chip"
              title={s.title}
              onClick={() => onOpenSource?.(i)}
            >
              {citationLabel(s, i + 1)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function MermaidBlock({ chart }: { chart: string }) {
  const reactId = useId().replace(/:/g, "");
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    setSvg(null);

    void (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "neutral",
        });
        const id = `mermaid-${reactId}-${Math.random().toString(36).slice(2, 8)}`;
        const { svg: rendered } = await mermaid.render(id, chart);
        if (!cancelled) setSvg(rendered);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [chart, reactId]);

  if (failed) {
    return (
      <pre>
        <code className="language-mermaid">{chart}</code>
      </pre>
    );
  }

  if (!svg) {
    return (
      <div className="mermaid-wrap text-xs text-label-tertiary">Rendering diagram…</div>
    );
  }

  return (
    <div
      className="mermaid-wrap"
      // Mermaid output is SVG from a local render with securityLevel strict.
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

/** Full citation for tooltips and the References list, e.g.
 *  "RBI (Digital Lending) Directions, 2025, Para 5.3 — Reserve Bank of India (effective 2025-05-08)". */
export function fullCitation(src: ChatSource | undefined): string {
  if (!src) return "";
  const parts = [src.title, src.section_label].filter(Boolean).join(", ");
  const issuer = src.issuer && src.issuer !== src.title ? ` — ${src.issuer}` : "";
  const effective = src.effective_date ? ` (effective ${src.effective_date})` : "";
  return `${parts}${issuer}${effective}`;
}

export function citationLabel(src: ChatSource | undefined, index1: number): string {
  // A provision label is checked before `page`: for a regulatory clause the
  // provision is the citation, and "Page 4" of a 200-page master direction is
  // not something a lawyer can verify.
  if (src?.section_label) return src.section_label;
  if (src?.page && src.page > 0) return `Page ${src.page}`;
  if (src && (src.kind === "template" || src.kind === "executed") && src.storage_key) {
    return `Source ${index1}`;
  }
  if (src?.kind === "attachment") return `Doc ${index1}`;
  if (src?.kind === "web") return `Web ${index1}`;
  if (src?.kind === "regulation") return `Reg ${index1}`;
  return `[${index1}]`;
}

function firstSourceIndex(
  sources: ChatSource[],
  kinds: ChatSource["kind"][],
): number {
  return sources.findIndex((s) => kinds.includes(s.kind));
}

function hasBareCitations(text: string): boolean {
  return /(?<![\]\w/])\[\d+\](?!\()/.test(text);
}

/**
 * Turn ``[n]`` and common source labels into markdown links the ``a`` renderer
 * turns into chips. Uses ``legalos://source/N`` (no nested ``[[n]]``) so GFM
 * does not swallow the citation.
 */
function linkifyCitations(text: string, sources: ChatSource[]): string {
  if (!text) return text;
  let out = text;

  // Groundedness marker — not a real cite; render as an amber warning chip.
  out = out.replace(
    /\*?\[unverified\]\*?/gi,
    "[unverified](legalos://unverified)",
  );

  if (sources.length) {
    // Numeric cites: [1], [2], … → [Page/Source label](legalos://source/n)
    out = out.replace(/(?<![\]\w/])\[(\d+)\](?!\()/g, (full, num: string) => {
      const n = Number(num);
      if (!Number.isFinite(n) || n < 1 || n > sources.length) return full;
      const label = citationLabel(sources[n - 1], n).replace(/[\[\]]/g, "");
      return `[${label}](legalos://source/${n})`;
    });

    // Model source-kind labels (from retrieval_policy) → first matching source
    const labelMap: { re: RegExp; kinds: ChatSource["kind"][] }[] = [
      {
        re: /(?:\[\s*JFPSL\s+executed(?:\s+contract)?\s*\]|\*\*JFPSL\s+executed(?:\s+contract)?\*\*)/gi,
        kinds: ["executed"],
      },
      {
        re: /(?:\[\s*JFPSL\s+template\s*\]|\*\*JFPSL\s+template\*\*)/gi,
        kinds: ["template", "executed"],
      },
      {
        re: /(?:\[\s*attached\s+document\s*\]|\*\*attached\s+document\*\*)/gi,
        kinds: ["attachment"],
      },
      {
        re: /(?:\[\s*external\/web\s*\]|\*\*external\/web\*\*)/gi,
        kinds: ["web"],
      },
    ];
    for (const { re, kinds } of labelMap) {
      const idx = firstSourceIndex(sources, kinds);
      if (idx < 0) continue;
      const n = idx + 1;
      const label = citationLabel(sources[idx], n).replace(/[\[\]]/g, "");
      out = out.replace(re, `[${label}](legalos://source/${n})`);
    }
  }

  return out;
}

function childrenToText(children: ReactNode): string {
  if (children == null || typeof children === "boolean") return "";
  if (typeof children === "string" || typeof children === "number") return String(children);
  if (Array.isArray(children)) return children.map(childrenToText).join("");
  return "";
}
