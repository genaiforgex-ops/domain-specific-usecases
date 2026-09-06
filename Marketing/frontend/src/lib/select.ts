// Row ordering by recency, on the common `updated_at` field. Action queues run
// oldest-first (work the oldest request first); views run newest-first.
export const byOldest = <T extends { updated_at: string }>(a: T, b: T) => a.updated_at.localeCompare(b.updated_at);
export const byNewest = <T extends { updated_at: string }>(a: T, b: T) => b.updated_at.localeCompare(a.updated_at);

export const fmtINR = (n: number) =>
  n >= 100000 ? `₹${(n / 100000).toFixed(n % 100000 === 0 ? 0 : 1)}L` : `₹${n.toLocaleString('en-IN')}`;

export const fmtDate = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
};

// Relative time against the real clock — for live data like notifications.
export const timeAgo = (iso: string) => {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
};
