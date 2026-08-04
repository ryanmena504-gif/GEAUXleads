import React from "react";
import { LANE_LABEL } from "@/lib/constants";

/**
 * LaneBadge — small pill showing which of the three parallel funnels a lead
 * belongs to. Colored per lane for at-a-glance triage.
 *   market_capture -> amber   (project leads, the default hunter output)
 *   partner        -> emerald (relationship/referral network)
 *   non_permit     -> sky     (public non-permit signals — not a green light)
 */
const LANE_STYLES = {
  market_capture: "bg-amber-500/12 text-amber-300 border-amber-500/30",
  partner: "bg-emerald-500/12 text-emerald-300 border-emerald-500/30",
  non_permit: "bg-sky-500/12 text-sky-300 border-sky-500/30",
};

export const LaneBadge = ({ lane, size = "sm", className = "" }) => {
  if (!lane) return null;
  const label = LANE_LABEL[lane] || lane;
  const style = LANE_STYLES[lane] || "border-neutral-700 text-neutral-300";
  const px = size === "md" ? "px-2.5 py-1 text-[11px]" : "px-2 py-0.5 text-[10px]";
  return (
    <span
      data-testid={`lane-badge-${lane}`}
      className={`mono uppercase tracking-widest rounded border inline-flex items-center ${px} ${style} ${className}`}
    >
      {label}
    </span>
  );
};

export default LaneBadge;
