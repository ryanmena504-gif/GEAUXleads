import React from "react";
import clsx from "clsx";

const statusStyles = {
  New: "bg-blue-500/10 text-blue-400 border-blue-500/25",
  "Needs research": "bg-amber-500/10 text-amber-300 border-amber-500/25",
  Ready: "bg-emerald-500/10 text-emerald-400 border-emerald-500/25",
  "Conversation started": "bg-sky-500/10 text-sky-300 border-sky-500/25",
  "Estimate requested": "bg-indigo-500/10 text-indigo-300 border-indigo-500/25",
  "Estimate sent": "bg-violet-500/10 text-violet-300 border-violet-500/25",
  Won: "bg-emerald-600/15 text-emerald-300 border-emerald-500/40",
  Lost: "bg-red-500/10 text-red-400 border-red-500/25",
  Disqualified: "bg-neutral-500/10 text-neutral-400 border-neutral-500/25",
};

export const StatusBadge = ({ status, className }) => (
  <span
    data-testid={`status-badge`}
    className={clsx(
      "inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-[11px] font-medium",
      statusStyles[status] || "bg-neutral-500/10 text-neutral-400 border-neutral-500/25",
      className,
    )}
  >
    <span className="w-1.5 h-1.5 rounded-full bg-current" />
    {status || "—"}
  </span>
);

export default StatusBadge;
