import { Badge } from "@/components/ui/Badge";
import { classNames, formatDate, statusColor } from "@/lib/utils";
import type { RegulatoryUpdate } from "@/types";

function statusBorderColor(status: string): string {
  switch (status) {
    case "action_required":
      return "border-l-warning";
    case "for_information":
      return "border-l-accent";
    case "not_relevant":
      return "border-l-label-tertiary";
    default:
      return "border-l-separator";
  }
}

function RelevanceBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  return (
    <div className="flex items-center gap-2 min-w-[5rem]">
      <div className="flex-1 h-1.5 rounded-full bg-bg-secondary overflow-hidden">
        <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-label-tertiary tabular-nums w-8 text-right">{pct}%</span>
    </div>
  );
}

export function NewsListItem({
  item,
  selected,
  onSelect,
}: {
  item: RegulatoryUpdate;
  selected: boolean;
  onSelect: (id: number) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(item.id)}
      className={classNames(
        "w-full text-left rounded-lg border border-separator/40 bg-bg shadow-card",
        "border-l-4 px-4 py-3 transition-colors duration-fast",
        statusBorderColor(item.status),
        selected
          ? "bg-bg-accent border-accent/30 ring-1 ring-accent/20"
          : "hover:bg-bg-secondary",
      )}
    >
      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
        <Badge className="bg-bg-secondary text-label-secondary border-separator/40 text-xs">
          {item.source}
        </Badge>
        {item.category && (
          <Badge className="bg-accent/10 text-accent border-accent/20 text-xs">{item.category}</Badge>
        )}
        <Badge className={classNames(statusColor(item.status), "text-xs")}>
          {item.status.replace(/_/g, " ")}
        </Badge>
      </div>
      <h3 className="font-medium text-label line-clamp-2 leading-snug">{item.title}</h3>
      <p className="text-sm text-label-secondary mt-1 line-clamp-1">{item.summary}</p>
      <div className="flex items-center justify-between gap-3 mt-2">
        <span className="text-xs text-label-tertiary">{formatDate(item.published_at)}</span>
        <RelevanceBar score={item.relevance_score} />
      </div>
    </button>
  );
}
