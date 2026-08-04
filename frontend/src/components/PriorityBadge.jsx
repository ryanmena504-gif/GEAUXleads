import React from "react";
import clsx from "clsx";

/**
 * PriorityBand + PriorityScore — quiet, tabular. No emoji, no glowing dots.
 * Fit reads as a small chip beside the numeric score.
 */
const bandStyles = {
  A: { fg: "var(--bh-olive)", bg: "var(--bh-olive-mute)", border: "rgba(107,122,85,0.35)" },
  B: { fg: "var(--bh-brass)", bg: "var(--bh-brass-mute)", border: "var(--bh-hair-warm)" },
  C: { fg: "#8f7a4b",         bg: "rgba(184,153,106,0.14)", border: "rgba(184,153,106,0.30)" },
  D: { fg: "var(--bh-clay)",  bg: "var(--bh-clay-mute)",    border: "rgba(165,90,62,0.28)" },
};

export const PriorityBand = ({ band, className }) => {
  const s = bandStyles[band];
  const style = s ? { color: s.fg, background: s.bg, borderColor: s.border }
                  : { color: "var(--bh-ink-mute)", background: "var(--bh-surface-2)", borderColor: "var(--bh-hair)" };
  return (
    <span
      data-testid={`priority-band-${band}`}
      className={clsx(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10.5px] font-medium tracking-[0.02em]",
        className,
      )}
      style={style}
    >
      <span
        aria-hidden
        className="w-1.5 h-1.5 rounded-full"
        style={{ background: s ? s.fg : "var(--bh-ink-mute)" }}
      />
      Fit {band || "—"}
    </span>
  );
};

export const PriorityScore = ({ score, band, size = "md" }) => {
  const has = typeof score === "number" && !Number.isNaN(score);
  const color = bandStyles[band]?.fg || "var(--bh-ink)";
  const sizeCls =
    size === "lg" ? "text-4xl"
    : size === "sm" ? "text-lg"
    : "text-[28px]";
  if (!has) {
    return (
      <div className="flex items-baseline gap-1" data-testid="priority-score-empty">
        <span className="text-[11px] tracking-tight text-[var(--bh-ink-mute)] italic">
          Needs scoring
        </span>
      </div>
    );
  }
  return (
    <div className="flex items-baseline gap-1" data-testid="priority-score">
      <span
        className={clsx("font-display tabular-nums leading-none", sizeCls)}
        style={{ color }}
      >
        {score}
      </span>
      <span className="text-[10.5px] text-[var(--bh-ink-mute)] tabular-nums">
        /100
      </span>
    </div>
  );
};
