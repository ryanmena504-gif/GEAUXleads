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
  accent = false,
  onClick,
  testId,
  icon: Icon,
  loading = false,
}) => (
  <button
    type="button"
    onClick={loading ? undefined : onClick}
    disabled={loading}
    data-testid={testId}
    data-loading={loading ? "true" : "false"}
    className={clsx(
      "group relative text-left w-full bh-surface rounded-md p-4 lg:p-5",
      "transition-colors duration-150 border-t",
      loading ? "cursor-progress" : "hover:bg-white/[0.03]",
      accent ? "border-t-amber-500/60" : "border-t-white/10",
    )}
  >
    <div className="flex items-start justify-between gap-2">
      <div className="flex items-center gap-2 text-neutral-400">
        {Icon ? <Icon size={13} strokeWidth={2} /> : null}
        <div className="mono uppercase tracking-[0.2em] text-[10px]">{label}</div>
      </div>
      <ArrowUpRight
        size={14}
        className="text-neutral-600 group-hover:text-amber-400 transition-colors duration-150"
        strokeWidth={2}
      />
    </div>
    {loading ? (
      <div
        className="mt-4 h-8 lg:h-9 w-2/3 rounded bg-white/[0.06] animate-pulse"
        aria-label={`${label} loading`}
      />
    ) : (
      <div className="mt-3 font-display text-3xl lg:text-4xl font-bold tracking-tight text-neutral-100 tabular-nums">
        {value}
      </div>
    )}
    {loading ? (
      <div className="mt-2.5 h-3 w-1/2 rounded bg-white/[0.04] animate-pulse" />
    ) : hint ? (
      <div className="mt-1.5 text-xs text-neutral-500">{hint}</div>
    ) : null}
  </button>
);

export default MetricCard;
