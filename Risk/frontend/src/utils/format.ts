export function formatLabel(slug: string | null | undefined): string {
  if (!slug) return "—";
  return slug
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatPercent(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${Math.round(value * 100)}%`;
}

export function formatStatus(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function riskBand(score: number): { label: string; level: "low" | "medium" | "high" | "critical" } {
  if (score <= 5) return { label: "Low", level: "low" };
  if (score <= 12) return { label: "Medium", level: "medium" };
  if (score <= 20) return { label: "High", level: "high" };
  return { label: "Critical", level: "critical" };
}

export function redFlagLevel(score: number | null): "low" | "medium" | "high" | "critical" {
  if (score == null) return "low";
  if (score < 25) return "low";
  if (score < 50) return "medium";
  if (score < 75) return "high";
  return "critical";
}
