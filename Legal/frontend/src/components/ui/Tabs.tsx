import { classNames } from "@/lib/utils";

export interface TabItem {
  id: string;
  label: string;
  count?: number;
}

/** Underline tab strip (mirrors the ViewTab pattern used across the app). */
export function Tabs({
  tabs,
  active,
  onChange,
  className,
}: {
  tabs: TabItem[];
  active: string;
  onChange: (id: string) => void;
  className?: string;
}) {
  return (
    <div className={classNames("flex gap-1 border-b border-separator/40 overflow-x-auto", className)}>
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          onClick={() => onChange(t.id)}
          className={classNames(
            "flex items-center gap-1.5 whitespace-nowrap border-b-2 -mb-px px-3.5 py-2.5 text-sm font-medium transition-colors duration-fast",
            active === t.id
              ? "border-accent text-accent"
              : "border-transparent text-label-secondary hover:text-label",
          )}
        >
          {t.label}
          {typeof t.count === "number" && (
            <span
              className={classNames(
                "rounded-md px-1.5 py-0.5 text-xs tabular-nums",
                active === t.id ? "bg-accent/10 text-accent" : "bg-bg-secondary text-label-tertiary",
              )}
            >
              {t.count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
