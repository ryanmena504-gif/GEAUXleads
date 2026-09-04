import React from "react";
import { Clock } from "lucide-react";

/**
 * DaysOnTable — small brass-hued badge showing how long a discovery
 * record has lived in the queue. Sourced from Airtable's `createdTime`
 * metadata via the backend `days_on_table` field. Colors escalate as
 * records grow stale so aging leads don't disappear into the middle of
 * the feed.
 */

const tone = (days) => {
  if (days == null) return { fg: "var(--bh-ink-mute)", bg: "var(--bh-surface-2)" };
  if (days === 0) return { fg: "var(--bh-olive)", bg: "var(--bh-olive-mute)" };
  if (days <= 3) return { fg: "var(--bh-brass)", bg: "var(--bh-brass-mute)" };
  if (days <= 14) return { fg: "var(--bh-ink-2)", bg: "var(--bh-surface-2)" };
  return { fg: "#8a5a45", bg: "rgba(138,90,69,0.10)" };
};

const label = (days) => {
  if (days == null) return "New";
  if (days === 0) return "Today";
  if (days === 1) return "1 day";
  return `${days} days`;
};

export const DaysOnTable = ({ days, testId }) => {
  const t = tone(days);
  return (
    <span
      data-testid={testId || "days-on-table"}
      className="inline-flex items-center gap-1 rounded-full px-2 py-[1px] text-[10px] font-medium tabular-nums whitespace-nowrap"
      style={{ color: t.fg, background: t.bg }}
      title={days == null ? "Freshly seen" : `On the table for ${days} day${days === 1 ? "" : "s"}`}
    >
      <Clock size={9} strokeWidth={2} />
      {label(days)}
    </span>
  );
};

export default DaysOnTable;
