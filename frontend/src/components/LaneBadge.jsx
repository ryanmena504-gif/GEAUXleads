import React from "react";
import { LANE_LABEL } from "@/lib/constants";

/**
 * LaneBadge — quiet material chip. No color alarms, just a soft tone per lane
 * that reads well against the bone canvas.
 */
const LANE_STYLES = {
  market_capture: { fg: "var(--bh-brass)", bg: "var(--bh-brass-mute)", border: "var(--bh-hair-warm)" },
  partner:        { fg: "var(--bh-olive)", bg: "var(--bh-olive-mute)", border: "rgba(107,122,85,0.32)" },
  landlord:       { fg: "#3f6b6b",         bg: "rgba(63,107,107,0.10)", border: "rgba(63,107,107,0.30)" },
  non_permit:     { fg: "#4b6b6f",         bg: "rgba(75,107,111,0.10)", border: "rgba(75,107,111,0.30)" },
};

// Softer, non-tactical labels shown in the UI. Backend key unchanged.
const DISPLAY_LABEL = {
  market_capture: "Project",
  partner: "Person to know",
  landlord: "Landlord",
  non_permit: "Watching",
};

export const LaneBadge = ({ lane, size = "sm", className = "" }) => {
  if (!lane) return null;
  const label = DISPLAY_LABEL[lane] || LANE_LABEL[lane] || lane;
  const s = LANE_STYLES[lane] || { fg: "var(--bh-ink-mute)", bg: "var(--bh-surface-2)", border: "var(--bh-hair)" };
  const px = size === "md" ? "px-2.5 py-1 text-[11px]" : "px-2 py-0.5 text-[10.5px]";
  return (
    <span
      data-testid={`lane-badge-${lane}`}
      className={`inline-flex items-center rounded-full border font-medium tracking-tight ${px} ${className}`}
      style={{ color: s.fg, background: s.bg, borderColor: s.border }}
    >
      {label}
    </span>
  );
};

export default LaneBadge;
