import React from "react";
import { Zap, Snowflake, Sparkles, CalendarClock } from "lucide-react";

const Card = ({ icon: I, label, value, hint, tone = "default", testId }) => {
  const TONE = {
    default: { color: "var(--bh-ink)", accent: "var(--bh-brass)" },
    warn:    { color: "var(--bh-ink)", accent: "#8a5a45" },
    cool:    { color: "var(--bh-ink)", accent: "#3f6b6b" },
  }[tone];
  return (
    <div
      data-testid={testId}
      className="rounded-md border bh-hairline p-3 flex flex-col gap-1"
      style={{ background: "var(--bh-surface-2)" }}
    >
      <div className="flex items-center gap-1.5">
        <I size={12} style={{ color: TONE.accent }} />
        <span className="mono uppercase tracking-widest text-[9.5px] text-[var(--bh-ink-mute)]">
          {label}
        </span>
      </div>
      <div
        className="font-display text-[22px] tabular-nums leading-none"
        style={{ color: TONE.color }}
      >
        {value ?? "—"}
      </div>
      {hint && (
        <div className="text-[10.5px] text-[var(--bh-ink-3)] leading-snug mt-0.5">
          {hint}
        </div>
      )}
    </div>
  );
};

/**
 * Derives four counters from the already-loaded opportunity list.
 * Zero-fabrication: every value is a straight count of existing records.
 */
export const CommandCenterStats = ({ items }) => {
  if (!Array.isArray(items)) return null;
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();

  const ready = items.filter((o) => o.current_queue === "Ready to Contact").length;
  const enrich = items.filter(
    (o) =>
      o.current_queue !== "Ready to Contact" &&
      o.current_queue !== "Contacted" &&
      typeof o.governed_priority_score !== "number" &&
      !o.email && !o.phone && !o.email_alt && !o.phone_alt,
  ).length;
  const fresh = items.filter((o) => (o.freshness || "").toLowerCase() === "fresh").length;
  const followups = items.filter((o) => {
    const d = o.next_follow_up;
    return d && d <= new Date(now.getTime() + 24 * 3600 * 1000).toISOString() && d >= startOfToday;
  }).length;

  return (
    <div
      data-testid="cc-stats"
      className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4"
    >
      <Card icon={Zap} label="Ready" value={ready} tone="default" testId="cc-stats-ready"
            hint={ready === 0 ? "Waiting on Claude to flip a queue" : "Highest-priority first"} />
      <Card icon={Snowflake} label="Needs enrichment" value={enrich} tone="cool" testId="cc-stats-enrich"
            hint={enrich === 0 ? "Pipeline is enriched" : "No score + no contact"} />
      <Card icon={Sparkles} label="Fresh" value={fresh} tone="warn" testId="cc-stats-fresh"
            hint={fresh === 0 ? "Nothing new since last check" : "Newest signals"} />
      <Card icon={CalendarClock} label="Follow-ups today" value={followups} tone="default" testId="cc-stats-followups"
            hint={followups === 0 ? "No follow-ups scheduled today" : "Due in next 24h"} />
    </div>
  );
};

export default CommandCenterStats;
