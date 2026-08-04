import React from "react";
import { Link } from "react-router-dom";

/**
 * Bloodhound mark — quiet geometric.
 *  - Two nested rounded squares (a plate + inset), aged brass hairline.
 *  - A single soft dot at the intersection reads like a builder's benchmark.
 * No shields, crosshairs, radar, or animal iconography.
 */
const Mark = ({ size = 32 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 32 32"
    role="img"
    aria-label="Bloodhound"
    className="shrink-0"
  >
    <rect
      x="3.5"
      y="3.5"
      width="25"
      height="25"
      rx="6"
      fill="var(--bh-surface)"
      stroke="var(--bh-brass)"
      strokeOpacity="0.7"
      strokeWidth="1.25"
    />
    <rect
      x="9"
      y="9"
      width="14"
      height="14"
      rx="3"
      fill="none"
      stroke="var(--bh-brass)"
      strokeOpacity="0.6"
      strokeWidth="1.15"
    />
    <circle cx="16" cy="16" r="1.6" fill="var(--bh-brass)" />
  </svg>
);

export const BloodhoundLogo = ({ compact = false }) => {
  if (compact) {
    return (
      <Link to="/" className="inline-flex items-center gap-2">
        <Mark size={28} />
      </Link>
    );
  }
  return (
    <Link to="/" className="inline-flex items-center gap-3 group">
      <Mark size={34} />
      <div className="leading-tight">
        <div className="font-display text-[19px] text-[var(--bh-ink)] tracking-tight">
          Bloodhound
        </div>
        <div className="text-[11px] text-[var(--bh-ink-mute)] tracking-tight">
          Owner-operated project book
        </div>
      </div>
    </Link>
  );
};

export default BloodhoundLogo;
