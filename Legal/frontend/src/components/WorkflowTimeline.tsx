import { classNames } from "@/lib/utils";

const STEPS: Array<{ key: string; label: string; statuses: string[] }> = [
  { key: "upload", label: "Upload", statuses: ["draft", "uploaded"] },
  { key: "review", label: "AI Review", statuses: ["under_review"] },
  { key: "redline", label: "Redline", statuses: ["redlined"] },
  { key: "send", label: "Sent to Vendor", statuses: ["sent_to_vendor"] },
  { key: "negotiate", label: "Negotiation", statuses: ["negotiation"] },
  { key: "execute", label: "Executed", statuses: ["executed"] },
];

function indexFor(status: string): number {
  const idx = STEPS.findIndex((s) => s.statuses.includes(status));
  return idx < 0 ? 0 : idx;
}

export function WorkflowTimeline({ status }: { status: string }) {
  const currentIdx = indexFor(status);

  return (
    <div className="bg-bg border border-separator/40 rounded-lg px-4 py-3">
      <div className="flex items-center" role="list" aria-label="Negotiation progress">
        {STEPS.map((step, i) => {
          const done = i < currentIdx;
          const active = i === currentIdx;
          return (
            <div key={step.key} className="flex items-center flex-1 last:flex-none" role="listitem">
              <div className="flex flex-col items-center text-center min-w-0">
                <div
                  className={classNames(
                    "w-8 h-8 rounded-full flex items-center justify-center text-caption font-semibold border-2 transition",
                    done && "bg-success border-success text-white",
                    active && "bg-accent border-accent text-white ring-4 ring-accent/20",
                    !done && !active && "bg-bg border-separator/60 text-label-tertiary",
                  )}
                  aria-current={active ? "step" : undefined}
                >
                  {done ? (
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    i + 1
                  )}
                </div>
                <div
                  className={classNames(
                    "text-caption font-medium mt-1 truncate",
                    active ? "text-accent" : done ? "text-label-secondary" : "text-label-tertiary",
                  )}
                >
                  {step.label}
                </div>
              </div>
              {i < STEPS.length - 1 && (
                <div
                  className={classNames(
                    "flex-1 h-0.5 mx-2 mt-[-14px]",
                    i < currentIdx ? "bg-success" : "bg-separator/40",
                  )}
                  aria-hidden
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
