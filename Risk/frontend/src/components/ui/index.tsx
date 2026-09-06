import { ReactNode, ButtonHTMLAttributes, forwardRef, useEffect, useState } from "react";
import { formatStatus } from "../../utils/format";

// Charm: animate a number counting up to its target on mount. Falls straight
// to the final value when the user prefers reduced motion.
function useCountUp(target: number, durationMs = 900) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setValue(target);
      return;
    }
    let raf = 0;
    let start = 0;
    const step = (ts: number) => {
      if (!start) start = ts;
      const p = Math.min(1, (ts - start) / durationMs);
      const eased = 1 - Math.pow(1 - p, 3); // ease-out cubic
      setValue(Math.round(target * eased));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, durationMs]);
  return value;
}

export function Badge({
  children,
  variant = "neutral",
}: {
  children: ReactNode;
  variant?: "neutral" | "success" | "warning" | "danger" | "info" | "ai";
}) {
  return <span className={`badge badge--${variant}`}>{children}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  const v =
    status === "confirmed" || status === "signed_off"
      ? "success"
      : status === "ready"
        ? "info"
        : status === "processing" || status === "pending"
          ? "warning"
          : status === "failed"
            ? "danger"
            : "neutral";
  return <Badge variant={v}>{formatStatus(status)}</Badge>;
}

export function RiskBadge({ level }: { level: "low" | "medium" | "high" | "critical" }) {
  return <Badge variant={level === "low" ? "success" : level === "medium" ? "warning" : "danger"}>{level}</Badge>;
}

export function Spinner({
  size = "md",
  onAccent = false,
}: {
  size?: "sm" | "md" | "lg";
  onAccent?: boolean;
}) {
  return (
    <span
      className={`spinner spinner--${size} ${onAccent ? "spinner--on-accent" : ""}`}
      role="status"
      aria-label="Loading"
    />
  );
}

export function Button({
  children,
  variant = "primary",
  size = "md",
  loading = false,
  className = "",
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
}) {
  return (
    <button
      type="button"
      className={`btn btn--${variant} btn--${size} ${className}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading && <Spinner size="sm" onAccent={variant === "primary"} />}
      {children}
    </button>
  );
}

export function Card({
  children,
  className = "",
  padding = true,
  ...rest
}: {
  children: ReactNode;
  className?: string;
  padding?: boolean;
  // Remaining div attributes pass through, so callers can anchor a card with an
  // `id` or make it draggable without this component growing a prop per use.
} & Omit<React.HTMLAttributes<HTMLDivElement>, "className" | "children">) {
  return (
    <div className={`card ${padding ? "card--padded" : ""} ${className}`} {...rest}>
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  action,
  breadcrumb,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  breadcrumb?: string;
}) {
  return (
    <header className="page-header">
      <div className="page-header__text">
        {breadcrumb && <span className="page-header__crumb">{breadcrumb}</span>}
        <h1>{title}</h1>
        {subtitle && <p className="page-header__sub">{subtitle}</p>}
      </div>
      {action && <div className="page-header__action">{action}</div>}
    </header>
  );
}

export function StatCard({
  label,
  value,
  hint,
  trend,
  icon,
  accent = "blue",
}: {
  label: string;
  value: string | number;
  hint?: string;
  trend?: string;
  icon?: ReactNode;
  accent?: "blue" | "amber" | "rose" | "emerald";
}) {
  const numeric = typeof value === "number" && Number.isFinite(value) ? value : null;
  const counted = useCountUp(numeric ?? 0);
  const display = numeric != null ? counted : value;
  return (
    <div className={`stat-card stat-card--${accent}`}>
      <div className="stat-card__top">
        {icon && <span className="stat-card__icon">{icon}</span>}
        <span className="stat-card__label">{label}</span>
      </div>
      <div className="stat-card__value">{display}</div>
      {(hint || trend) && (
        <div className="stat-card__footer">
          {hint && <span className="stat-card__hint">{hint}</span>}
          {trend && <span className="stat-card__trend">{trend}</span>}
        </div>
      )}
    </div>
  );
}

export function RiskMeter({ score, max = 100, label }: { score: number | null; max?: number; label?: string }) {
  const pct = score != null ? Math.min(100, (score / max) * 100) : 0;
  const level = pct < 25 ? "low" : pct < 50 ? "medium" : pct < 75 ? "high" : "critical";
  return (
    <div className="risk-meter">
      <div className="risk-meter__header">
        <span>{label ?? "Risk score"}</span>
        <strong>{score != null ? score.toFixed(1) : "—"}</strong>
      </div>
      <div className="risk-meter__track" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className={`risk-meter__fill risk-meter__fill--${level}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// Circular gauge — animated ring with the score in the middle, colored by band.
export function Gauge({
  score,
  max = 100,
  caption,
  size = 140,
}: {
  score: number | null;
  max?: number;
  caption?: string;
  size?: number;
}) {
  const pct = score != null ? Math.min(100, Math.max(0, (score / max) * 100)) : 0;
  const level = pct < 25 ? "low" : pct < 50 ? "medium" : pct < 75 ? "high" : "critical";
  const color =
    level === "low" ? "var(--color-success)"
    : level === "medium" ? "var(--color-warning)"
    : level === "high" ? "#FF6B00"
    : "var(--color-error)";

  const stroke = 12;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const counted = useCountUp(score != null ? Math.round(score) : 0);

  // Animate the arc sweeping in from empty on mount / value change.
  const [animPct, setAnimPct] = useState(0);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setAnimPct(pct);
      return;
    }
    const id = requestAnimationFrame(() => setAnimPct(pct));
    return () => cancelAnimationFrame(id);
  }, [pct]);

  return (
    <div className="gauge">
      <div className="gauge__ring" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
          <circle className="gauge__track" cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} />
          <circle
            className="gauge__progress"
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circ}
            strokeDashoffset={circ * (1 - animPct / 100)}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
          />
        </svg>
        <div className="gauge__center">
          <span className="gauge__value">{score != null ? counted : "—"}</span>
          <span className="gauge__max">of {max}</span>
        </div>
      </div>
      {caption && <span className="gauge__caption">{caption}</span>}
    </div>
  );
}

export function EmptyState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon" aria-hidden>◇</div>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}

export function DataTable({ children }: { children: ReactNode }) {
  return (
    <div className="table-wrap">
      <table className="data-table">{children}</table>
    </div>
  );
}

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: string; label: string }[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          aria-selected={active === t.id}
          className={`tabs__item ${active === t.id ? "tabs__item--active" : ""}`}
          onClick={() => onChange(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function FormField({
  label,
  children,
  hint,
  required,
}: {
  label: string;
  children: ReactNode;
  // ReactNode, not string: long guidance is passed in as a collapsible
  // <details> element rather than a plain line of text.
  hint?: ReactNode;
  required?: boolean;
}) {
  return (
    <label className="form-field">
      <span className="form-field__label">
        {label}
        {required && <span className="form-field__req" aria-hidden> *</span>}
      </span>
      {children}
      {hint && <span className="form-field__hint">{hint}</span>}
    </label>
  );
}

// forwardRef so callers can focus a specific control — the form wizard's
// "jump to the first unanswered question" needs a handle on the input itself.
export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  function Input(props, ref) {
    return <input ref={ref} className="input" {...props} />;
  },
);

export const Select = forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  function Select(props, ref) {
    return <select ref={ref} className="input input--select" {...props} />;
  },
);

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea(props, ref) {
  return <textarea ref={ref} className="input input--textarea" {...props} />;
});

export function Skeleton({
  width = "100%",
  height = 16,
  radius = 8,
  style,
}: {
  width?: number | string;
  height?: number | string;
  radius?: number;
  style?: React.CSSProperties;
}) {
  return <span className="skeleton" style={{ width, height, borderRadius: radius, ...style }} />;
}

// Placeholder rows for a DataTable while its data is loading, so the layout
// doesn't jump when real rows arrive.
export function TableSkeleton({ columns, rows = 4 }: { columns: number; rows?: number }) {
  return (
    <tbody>
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r}>
          {Array.from({ length: columns }).map((_, c) => (
            <td key={c}>
              <Skeleton width={c === 0 ? "70%" : "50%"} />
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  );
}

export function SplitLayout({ left, right }: { left: ReactNode; right: ReactNode }) {
  return (
    <div className="split-layout">
      <div className="split-layout__main">{left}</div>
      <aside className="split-layout__side">{right}</aside>
    </div>
  );
}

/** In-app replacement for window.confirm().
 *
 * The native dialog is unusable in a product: it renders chrome saying
 * "localhost:5174 says", cannot be styled, and blocks the main thread so no
 * loading state can be shown while the action it guards is in flight. This keeps
 * the same call-and-wait shape (open it, act on `onConfirm`) but stays inside the
 * app's own visual language.
 *
 * Destructive by default — every current caller is a delete or a deactivate.
 */
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Delete",
  cancelLabel = "Cancel",
  variant = "danger",
  loading = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "danger" | "primary";
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  // Escape closes, and focus lands on the dialog so the confirm button is one
  // Tab away — parity with the native dialog's keyboard behaviour, which is the
  // one thing it did well.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !loading) onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, loading, onCancel]);

  if (!open) return null;

  return (
    <div
      className="confirm-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
      // Clicking the backdrop cancels, but only the backdrop itself — a click
      // that started inside the panel must not fall through to here.
      onClick={(e) => {
        if (e.target === e.currentTarget && !loading) onCancel();
      }}
    >
      <div className="confirm-panel">
        <h2 className="confirm-panel__title" id="confirm-title">
          {title}
        </h2>
        {message && <p className="confirm-panel__message">{message}</p>}
        <div className="confirm-panel__actions">
          <Button variant="secondary" onClick={onCancel} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button variant={variant} onClick={onConfirm} loading={loading} autoFocus>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
