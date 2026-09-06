import { classNames } from "@/lib/utils";

import { parseRegulatoryText, regulatoryReadStats, type TextBlock } from "./formatRegulatoryText";

function BlockView({ block, index }: { block: TextBlock; index: number }) {
  if (block.type === "heading") {
    return (
      <h3
        className={classNames(
          "text-sm font-semibold text-label tracking-tight",
          index > 0 && "mt-5 pt-4 border-t border-separator/30",
        )}
      >
        {block.text}
      </h3>
    );
  }

  if (block.type === "list") {
    const Tag = block.ordered ? "ol" : "ul";
    return (
      <Tag
        className={classNames(
          "text-sm text-label leading-relaxed space-y-2 pl-5",
          block.ordered ? "list-decimal" : "list-disc",
        )}
      >
        {block.items.map((item, i) => (
          <li key={i} className="pl-1 marker:text-label-tertiary">
            {item}
          </li>
        ))}
      </Tag>
    );
  }

  return <p className="text-sm text-label leading-relaxed">{block.text}</p>;
}

export function NewsFullText({ text, url }: { text: string; url?: string | null }) {
  const blocks = parseRegulatoryText(text);
  const stats = regulatoryReadStats(text);
  const headings = blocks.filter((b) => b.type === "heading");

  return (
    <article className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 text-xs text-label-tertiary pb-3 border-b border-separator/30">
        <span>{stats.words.toLocaleString()} words</span>
        <span>·</span>
        <span>~{stats.minutes} min read</span>
        {url && (
          <>
            <span>·</span>
            <a href={url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
              Original source
            </a>
          </>
        )}
      </div>

      {headings.length > 1 && (
        <nav className="rounded-lg border border-separator/30 bg-bg-secondary/50 px-3 py-2.5">
          <div className="text-[10px] uppercase tracking-wider font-semibold text-label-secondary mb-1.5">
            Sections
          </div>
          <ul className="space-y-1">
            {headings.map((h, i) => (
              <li key={i} className="text-xs text-label-secondary truncate">
                {h.type === "heading" ? h.text : ""}
              </li>
            ))}
          </ul>
        </nav>
      )}

      <div className="space-y-3">
        {blocks.map((block, i) => (
          <BlockView key={i} block={block} index={i} />
        ))}
      </div>
    </article>
  );
}
