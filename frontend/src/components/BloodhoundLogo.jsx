import React from "react";

export const BloodhoundLogo = ({ compact = false }) => (
  <div className="flex items-center gap-2.5" data-testid="bloodhound-logo">
    <div className="relative w-7 h-7 flex items-center justify-center">
      <div className="absolute inset-0 rounded-sm border bh-hairline-strong" />
      <div className="absolute inset-[6px] rounded-full border border-amber-500/70" />
      <div className="absolute inset-[10px] rounded-full bg-amber-500 bh-pulse-dot" />
      <div className="absolute left-1/2 top-0 bottom-0 w-px bg-amber-500/25" />
      <div className="absolute top-1/2 left-0 right-0 h-px bg-amber-500/25" />
    </div>
    {!compact && (
      <div className="leading-tight">
        <div className="font-display text-[13px] font-bold tracking-[0.22em] text-neutral-100">
          BLOODHOUND
        </div>
        <div className="mono text-[9px] tracking-[0.28em] text-neutral-500 uppercase">
          Opportunity Intel
        </div>
      </div>
    )}
  </div>
);

export default BloodhoundLogo;
