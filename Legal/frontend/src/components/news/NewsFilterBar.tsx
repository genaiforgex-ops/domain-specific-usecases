import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { classNames } from "@/lib/utils";

import { CATEGORIES, REGULATORS } from "./constants";

export interface NewsFilters {
  regulator: string;
  category: string;
  status: string;
  q: string;
}

export function NewsFilterBar({
  filters,
  onChange,
  showStatus = true,
}: {
  filters: NewsFilters;
  onChange: (next: NewsFilters) => void;
  showStatus?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  const activeCount = [filters.regulator, filters.category, showStatus ? filters.status : ""].filter(
    Boolean,
  ).length;

  function clearFilters() {
    onChange({ regulator: "", category: "", status: "", q: filters.q });
  }

  function removeFilter(key: keyof NewsFilters) {
    onChange({ ...filters, [key]: "" });
  }

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  const chips: { key: keyof NewsFilters; label: string }[] = [];
  if (filters.regulator) chips.push({ key: "regulator", label: filters.regulator });
  if (filters.category) chips.push({ key: "category", label: filters.category });
  if (showStatus && filters.status) {
    chips.push({ key: "status", label: filters.status.replace(/_/g, " ") });
  }

  const selectFields = (
    <>
      <Select
        label="Regulator"
        value={filters.regulator}
        onChange={(e) => onChange({ ...filters, regulator: e.target.value })}
      >
        <option value="">All regulators</option>
        {REGULATORS.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </Select>
      <Select
        label="Category"
        value={filters.category}
        onChange={(e) => onChange({ ...filters, category: e.target.value })}
      >
        <option value="">All categories</option>
        {CATEGORIES.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </Select>
      {showStatus && (
        <Select
          label="Status"
          value={filters.status}
          onChange={(e) => onChange({ ...filters, status: e.target.value })}
        >
          <option value="">All statuses</option>
          <option value="action_required">Action required</option>
          <option value="for_information">For information</option>
          <option value="not_relevant">Not relevant</option>
        </Select>
      )}
    </>
  );

  return (
    <div className="space-y-3 relative z-10">
      <div className="flex flex-wrap items-end gap-2">
        <Input
          placeholder="Search updates…"
          value={filters.q}
          onChange={(e) => onChange({ ...filters, q: e.target.value })}
          className="flex-1 min-w-[12rem]"
        />

        {/* Desktop / tablet: always-visible filter selects (no overlap with nav) */}
        <div className="hidden md:grid md:grid-cols-2 xl:grid-cols-3 gap-2 w-full xl:w-auto xl:flex-1 min-w-0">
          {selectFields}
        </div>

        {/* Mobile: Filters popover — open to the right so it stays in the content pane */}
        <div className="relative md:hidden" ref={popoverRef}>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => setOpen((v) => !v)}
            className="whitespace-nowrap"
            aria-expanded={open}
            aria-haspopup="dialog"
          >
            Filters
            {activeCount > 0 && (
              <span className="ml-1.5 rounded-full bg-accent text-white px-1.5 py-0.5 text-xs">
                {activeCount}
              </span>
            )}
            <span className="ml-1 text-label-tertiary">{open ? "▴" : "▾"}</span>
          </Button>
          {open && (
            <div
              role="dialog"
              aria-label="News filters"
              className={classNames(
                "absolute left-0 top-full mt-1 z-[60] w-[min(18rem,calc(100vw-4.5rem))]",
                "rounded-lg border border-separator/50 bg-bg shadow-card p-3 space-y-3 animate-scale-in",
              )}
            >
              {selectFields}
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => setOpen(false)}
              >
                Done
              </Button>
            </div>
          )}
        </div>

        {activeCount > 0 && (
          <Button type="button" variant="ghost" size="sm" onClick={clearFilters}>
            Clear
          </Button>
        )}
      </div>

      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {chips.map((chip) => (
            <button
              key={chip.key}
              type="button"
              onClick={() => removeFilter(chip.key)}
              className={classNames(
                "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5",
                "text-xs bg-bg-secondary text-label-secondary border border-separator/40",
                "hover:bg-bg-accent transition-colors",
              )}
            >
              {chip.label}
              <span className="text-label-tertiary">×</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
