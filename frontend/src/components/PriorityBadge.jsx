import React from "react";
import clsx from "clsx";

const bandStyles = {
  A: "bg-emerald-500/10 text-emerald-400 border-emerald-500/25",
  B: "bg-blue-500/10 text-blue-400 border-blue-500/25",
  C: "bg-amber-500/10 text-amber-400 border-amber-500/25",
  D: "bg-red-500/10 text-red-400 border-red-500/25",
};

export const PriorityBand = ({ band, className }) => (
  <span
    data-testid={`priority-band-${band}`}
    className={clsx(
      "mono inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-semibold tracking-widest uppercase",
      bandStyles[band] || "bg-neutral-500/10 text-neutral-400 border-neutral-500/25",
      className,
    )}
  >
    <span className="w-1 h-1 rounded-full bg-current" />
    Band {band || "—"}
  </span>
);

export const PriorityScore = ({ score, band, size = "md" }) => {
  const color =
    band === "A"
      ? "text-emerald-400"
      : band === "B"
        ? "text-blue-400"
        : band === "C"
          ? "text-amber-400"
          : band === "D"
            ? "text-red-400"
            : "text-neutral-300";
  const sizeCls =
    size === "lg"
      ? "text-4xl"
      : size === "sm"
        ? "text-lg"
        : "text-2xl";
  return (
    <div className="flex items-baseline gap-1" data-testid="priority-score">
      <span className={clsx("mono font-semibold tabular-nums", color, sizeCls)}>
        {score ?? "—"}
      </span>
      <span className="mono text-[10px] text-neutral-500">/100</span>
    </div>
  );
};
