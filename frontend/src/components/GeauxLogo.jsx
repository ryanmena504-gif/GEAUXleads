import React from "react";
import { Link } from "react-router-dom";

// GEAUXleads mark — rounded plate, a "G" drawn as chevron + bar, one clay benchmark dot.
export const GeauxMark = ({ size = 32 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 32 32"
    role="img"
    aria-label="GEAUXleads"
    className="shrink-0"
    data-testid="geaux-logo-mark"
    fill="none"
  >
    <rect x="3" y="3" width="26" height="26" rx="7" fill="var(--bh-surface)" stroke="var(--bh-brass)" strokeWidth="1.6" />
    <path
      d="M21.3 10.7 A7.5 7.5 0 1 0 23.5 16 H17.5"
      stroke="var(--bh-brass)"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <circle cx="17.5" cy="16" r="1.9" fill="var(--bh-clay)" />
  </svg>
);

export const GeauxWordmark = ({ className = "text-[19px]" }) => (
  <span data-testid="geaux-wordmark" className={`font-display tracking-tight inline-flex items-baseline ${className}`}>
    <span className="font-extrabold text-[var(--bh-ink)]">GEAUX</span>
    <span className="font-normal text-[var(--bh-brass)]">leads</span>
  </span>
);

export const GeauxLogo = ({ compact = false }) => {
  if (compact) {
    return (
      <Link to="/" data-testid="geaux-logo-compact" className="inline-flex items-center gap-2">
        <GeauxMark size={28} />
      </Link>
    );
  }
  return (
    <Link to="/" data-testid="geaux-logo" className="inline-flex items-center gap-3 group">
      <GeauxMark size={34} />
      <div className="leading-tight">
        <GeauxWordmark />
        <div className="text-[11px] text-[var(--bh-ink-mute)] tracking-tight">
          Louisiana opportunity intelligence
        </div>
      </div>
    </Link>
  );
};

export default GeauxLogo;
