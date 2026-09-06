import { formatDate } from "@/lib/utils";
import type { ReviewChangeEntry } from "@/types";

export function ChangeHistoryPanel({ entries }: { entries: ReviewChangeEntry[] }) {
  if (!entries.length) {
    return (
      <div className="rounded-xl border border-separator/40 bg-bg px-4 py-3">
        <p className="text-sm font-semibold text-label">Change history</p>
        <p className="text-xs text-label-secondary mt-1">
          Decisions and applied edits will appear here.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-separator/40 bg-bg overflow-hidden">
      <div className="px-4 py-3 border-b border-separator/30">
        <p className="text-sm font-semibold text-label">Change history</p>
        <p className="text-xs text-label-secondary">{entries.length} event(s)</p>
      </div>
      <ul className="max-h-48 overflow-y-auto divide-y divide-separator/20">
        {[...entries].reverse().map((e, i) => (
          <li key={i} className="px-4 py-2 text-xs">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold text-label capitalize">{e.status}</span>
              <span className="text-label-secondary">{e.source.replace(/_/g, " ")}</span>
              {e.applied_at && (
                <span className="text-label-tertiary">{formatDate(e.applied_at)}</span>
              )}
            </div>
            {e.rationale && (
              <p className="text-label-secondary mt-0.5 line-clamp-2">{e.rationale}</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
