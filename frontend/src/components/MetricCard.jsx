import React from "react";
import clsx from "clsx";
import { ArrowUpRight } from "lucide-react";

/**
 * `loading` renders a skeleton instead of a value. Without it an unresolved
 * metric renders as 0 or a dash, which reads as "we looked and there is
 * nothing" rather than "we have not looked yet".
 */
export const MetricCard = ({
  label,
  value,
  hint,
  accent = false,      // brass hairline accent when the metric is the priority focus
  tone = "default",    // "olive" | "clay" | "sand" | "brass" | "default"
  onClick,
  testId,
  icon: Icon,
}) => {
  const toneClass =
    accent ? "bh-swatch--brass"
    : tone === "olive" ? "bh-swatch--olive"
    : tone === "clay" ? "bh-swatch--clay"
    : tone === "sand" ? "bh-swatch--sand"
    : tone === "brass" ? "bh-swatch--brass"
    : "";
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      className={clsx(
        "bh-swatch group relative text-left w-full p-5 lg:p-6",
        "transition-shadow duration-200",
        toneClass,
      )}
      style={{ minHeight: 132 }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 text-[var(--bh-ink-mute)]">
          {Icon ? <Icon size={14} strokeWidth={1.75} /> : null}
          <div className="bh-eyebrow">{label}</div>
        </div>
        <ArrowUpRight
          size={15}
          strokeWidth={1.5}
          className="text-[var(--bh-ink-faint)] group-hover:text-[var(--bh-brass)] transition-colors duration-150"
        />
      </div>
      <div className="mt-5 font-display text-[34px] lg:text-[38px] leading-none text-[var(--bh-ink)] tabular-nums">
        {value}
      </div>
      {hint ? (
        <div className="mt-2 text-[12.5px] text-[var(--bh-ink-mute)] tracking-tight">
          {hint}
        </div>
      ) : null}
    </button>
  );
};

export default MetricCard;
