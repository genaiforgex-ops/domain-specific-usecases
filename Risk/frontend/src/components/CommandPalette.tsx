import { useEffect, useState } from "react";
import { api } from "../api/client";

interface CommandPaletteProps {
  onClose: () => void;
  onNavigate: (path: string) => void;
}

export function CommandPalette({ onClose, onNavigate }: CommandPaletteProps) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<{
    vendors: Array<{ id: string; name: string }>;
    projects: Array<{ id: string; name: string }>;
  }>({ vendors: [], projects: [] });

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  useEffect(() => {
    if (q.length < 2) return;
    const t = setTimeout(() => {
      api
        .get<{ vendors: Array<{ id: string; name: string }>; projects: Array<{ id: string; name: string }> }>(
          `/search?q=${encodeURIComponent(q)}`
        )
        .then(setResults)
        .catch(() => setResults({ vendors: [], projects: [] }));
    }, 200);
    return () => clearTimeout(t);
  }, [q]);

  const items = [
    { label: "Home", path: "/" },
    { label: "M1 Classification", path: "/m1" },
    { label: "M2 Vendor DD", path: "/m2" },
    { label: "M3 Risk Scoring", path: "/m3" },
    ...results.vendors.map((v) => ({ label: `Vendor: ${v.name}`, path: `/m2?vendor=${v.id}` })),
    ...results.projects.map((p) => ({ label: `Project: ${p.name}`, path: `/m3?project=${p.id}` })),
  ].filter((i) => !q || i.label.toLowerCase().includes(q.toLowerCase()));

  return (
    // Clicking the backdrop dismisses, as a modal is expected to. Escape worked
    // already but nothing on screen said so, which left searching for something
    // as the only discoverable way out.
    <div
      className="palette-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="palette">
        <div className="palette__bar">
          <input
            type="search"
            placeholder="Jump to anything…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            autoFocus
            aria-label="Search"
          />
          <kbd className="palette__esc">Esc</kbd>
          <button
            type="button"
            className="palette__close"
            onClick={onClose}
            aria-label="Close search"
            title="Close search"
          >
            ✕
          </button>
        </div>
        <ul role="listbox">
          {items.slice(0, 12).map((item) => (
            <li key={item.path + item.label}>
              <button
                type="button"
                onClick={() => {
                  onNavigate(item.path);
                  onClose();
                }}
              >
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
