import React from "react";
import { ArrowUpNarrowWide, ArrowDownNarrowWide } from "lucide-react";

/**
 * DiscoverySortToggle — pair of pill buttons for Freshest / Oldest first.
 * Used on every Discovery feed. `value` is one of "fresh" | "stale".
 */
export const DiscoverySortToggle = ({ value, onChange, testId = "sort-toggle" }) => (
  <div
    data-testid={testId}
    className="inline-flex items-center rounded-md border bh-hairline overflow-hidden"
  >
    <button
      type="button"
      onClick={() => onChange("fresh")}
      data-testid={`${testId}-fresh`}
      className="inline-flex items-center gap-1.5 h-8 px-2.5 text-[11px] font-medium transition-colors"
      style={{
        background: value === "fresh" ? "var(--bh-brass)" : "var(--bh-surface)",
        color: value === "fresh" ? "var(--bh-surface)" : "var(--bh-ink-2)",
      }}
    >
      <ArrowDownNarrowWide size={11} strokeWidth={1.75} /> Freshest
    </button>
    <button
      type="button"
      onClick={() => onChange("stale")}
      data-testid={`${testId}-stale`}
      className="inline-flex items-center gap-1.5 h-8 px-2.5 text-[11px] font-medium transition-colors border-l bh-hairline"
      style={{
        background: value === "stale" ? "var(--bh-brass)" : "var(--bh-surface)",
        color: value === "stale" ? "var(--bh-surface)" : "var(--bh-ink-2)",
      }}
    >
      <ArrowUpNarrowWide size={11} strokeWidth={1.75} /> Oldest first
    </button>
  </div>
);

/**
 * sortByDays — small helper any Discovery page can call to apply the toggle.
 * Keeps `is_freshly_actionable` records glued to the top regardless of
 * direction so newly-enriched contacts never get buried under stale ones.
 */
export const sortByDays = (items, direction = "fresh") => {
  const arr = [...items];
  arr.sort((a, b) => {
    const freshDiff = (b.is_freshly_actionable ? 1 : 0) - (a.is_freshly_actionable ? 1 : 0);
    if (freshDiff !== 0) return freshDiff;
    const av = a.days_on_table == null ? Number.MAX_SAFE_INTEGER : a.days_on_table;
    const bv = b.days_on_table == null ? Number.MAX_SAFE_INTEGER : b.days_on_table;
    return direction === "stale" ? bv - av : av - bv;
  });
  return arr;
};

export default DiscoverySortToggle;
