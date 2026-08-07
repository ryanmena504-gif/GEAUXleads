import React from "react";
import clsx from "clsx";
import { priorityLevel } from "@/lib/priority";

/**
 * Priority — a plain-English pill (High / Medium / Low). Numeric scores are
 * intentionally not shown; contractors care about the ranking, not the math.
 *
 * PriorityBand and PriorityScore are kept as named exports for backward
 * compatibility with pages that still import them. Both now render the same
 * plain-English chip — the raw 0–100 number lives inside `title=` for hover.
 */
const LEVEL_STYLES = {
  High:   { fg: "var(--bh-olive)", bg: "var(--bh-olive-mute)", border: "rgba(107,122,85,0.35)" },
  Medium: { fg: "var(--bh-brass)", bg: "var(--bh-brass-mute)", border: "var(--bh-hair-warm)" },
  Low:    { fg: "#8f7a4b",         bg: "rgba(184,153,106,0.14)", border: "rgba(184,153,106,0.30)" },
};

export const PriorityPill = ({ band, score, className }) => {
  const level = priorityLevel(band, score);
  if (!level) {
    return (
      <span
        data-testid="priority-pill-empty"
        className={clsx(
          "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10.5px] tracking-tight italic",
          className,
        )}
        style={{ color: "var(--bh-ink-mute)", background: "var(--bh-surface-2)", borderColor: "var(--bh-hair)" }}
      >
        Priority pending
      </span>
    );
  }
  const s = LEVEL_STYLES[level];
  const hoverHint = typeof score === "number" ? `Score ${Math.round(score)}/100` : undefined;
  return (
    <span
      data-testid={`priority-pill-${level.toLowerCase()}`}
      title={hoverHint}
      className={clsx(
        "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border text-[11px] font-medium tracking-tight",
        className,
      )}
      style={{ color: s.fg, background: s.bg, borderColor: s.border }}
    >
      <span aria-hidden className="w-1.5 h-1.5 rounded-full" style={{ background: s.fg }} />
      {level} priority
    </span>
  );
};

// Back-compat aliases — same look. Pages using these get the new pill.
export const PriorityBand = ({ band, className }) => (
  <PriorityPill band={band} className={className} />
);

// PriorityScore now renders as a large plain-English label (High/Medium/Low)
// with the numeric score only visible on hover for anyone who wants it.
export const PriorityScore = ({ score, band, size = "md" }) => {
  const level = priorityLevel(band, score);
  const color = level ? LEVEL_STYLES[level].fg : "var(--bh-ink-mute)";
  const sizeCls =
    size === "lg" ? "text-[26px]"
    : size === "sm" ? "text-[13px]"
    : "text-[18px]";
  if (!level) {
    return (
      <div className="flex items-baseline gap-1" data-testid="priority-score-empty">
        <span className="text-[11px] tracking-tight text-[var(--bh-ink-mute)] italic">
          Pending
        </span>
      </div>
    );
  }
  return (
    <div className="flex items-baseline gap-1" data-testid="priority-score" title={typeof score === "number" ? `Score ${Math.round(score)}/100` : undefined}>
      <span
        className={clsx("font-display leading-none tracking-tight", sizeCls)}
        style={{ color }}
      >
        {level}
      </span>
    </div>
  );
};
