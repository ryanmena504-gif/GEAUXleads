import React from "react";
import clsx from "clsx";

const statusStyles = {
  New:                     { fg: "var(--bh-brass)",  bg: "var(--bh-brass-mute)",  border: "var(--bh-hair-warm)" },
  "Needs research":        { fg: "#7a6a4f",          bg: "rgba(122,106,79,0.12)", border: "rgba(122,106,79,0.28)" },
  Ready:                   { fg: "var(--bh-olive)",  bg: "var(--bh-olive-mute)",  border: "rgba(107,122,85,0.32)" },
  "Conversation started":  { fg: "#4b6b6f",          bg: "rgba(75,107,111,0.10)", border: "rgba(75,107,111,0.30)" },
  "Estimate requested":    { fg: "#5a5847",          bg: "rgba(90,88,71,0.12)",   border: "rgba(90,88,71,0.28)" },
  "Estimate sent":         { fg: "#6a5c85",          bg: "rgba(106,92,133,0.10)", border: "rgba(106,92,133,0.28)" },
  Won:                     { fg: "var(--bh-olive)",  bg: "rgba(107,122,85,0.18)", border: "rgba(107,122,85,0.45)" },
  Lost:                    { fg: "var(--bh-clay)",   bg: "var(--bh-clay-mute)",   border: "rgba(165,90,62,0.28)" },
  Disqualified:            { fg: "var(--bh-ink-mute)",bg: "var(--bh-surface-2)",  border: "var(--bh-hair)" },
};

export const StatusBadge = ({ status, className }) => {
  const s = statusStyles[status] || statusStyles.Disqualified;
  return (
    <span
      data-testid="status-badge"
      className={clsx(
        "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border text-[11.5px] font-medium tracking-tight",
        className,
      )}
      style={{ color: s.fg, background: s.bg, borderColor: s.border }}
    >
      <span
        aria-hidden
        className="w-1.5 h-1.5 rounded-full"
        style={{ background: s.fg }}
      />
      {status || "—"}
    </span>
  );
};

export default StatusBadge;
