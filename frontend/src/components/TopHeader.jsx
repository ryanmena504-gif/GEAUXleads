import React from "react";
import { Bell, Search } from "lucide-react";
import BloodhoundLogo from "@/components/BloodhoundLogo";
import { useCommandPalette } from "@/layouts/AppLayout";

export const TopHeader = ({ pageTitle, subtitle, right, mobileMenu }) => {
  const palette = useCommandPalette();
  const now = new Date();
  const dateStr = now.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  return (
    <header
      data-testid="top-header"
      className="sticky top-0 z-20 bh-surface border-b bh-hairline"
    >
      <div className="px-4 lg:px-8 h-16 flex items-center gap-4">
        <div className="lg:hidden">
          <BloodhoundLogo compact />
        </div>

        <div className="hidden lg:flex flex-col leading-tight">
          <div className="font-display text-xl font-bold text-neutral-100 tracking-tight">
            {pageTitle}
          </div>
          {subtitle ? (
            <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
              {subtitle}
            </div>
          ) : null}
        </div>

        <div className="flex-1" />

        <button
          type="button"
          onClick={() => palette.open()}
          data-testid="global-search"
          className="hidden md:flex items-center gap-2 bh-surface-2 rounded px-3 h-9 min-w-[240px] max-w-sm text-left hover:bg-white/[0.05] transition-colors duration-150"
        >
          <Search size={14} className="text-neutral-500" />
          <span className="text-sm flex-1 text-neutral-500">
            Search opportunities, addresses, permits…
          </span>
          <span className="mono text-[10px] text-neutral-500 border bh-hairline rounded px-1.5 py-0.5">
            ⌘K
          </span>
        </button>

        <button
          type="button"
          onClick={() => palette.open()}
          data-testid="mobile-search-btn"
          aria-label="Open command palette"
          className="md:hidden w-9 h-9 flex items-center justify-center rounded bh-surface-2 hover:bg-white/[0.05] transition-colors duration-150"
        >
          <Search size={15} className="text-neutral-300" />
        </button>

        <div className="hidden lg:flex items-center gap-3 text-xs text-neutral-400">
          <div className="mono uppercase tracking-widest text-[10px]">
            {dateStr}
          </div>
        </div>

        <button
          data-testid="notifications-btn"
          className="relative w-9 h-9 flex items-center justify-center rounded bh-surface-2 hover:bg-white/[0.05] transition-colors duration-150"
          aria-label="Notifications"
        >
          <Bell size={15} className="text-neutral-300" strokeWidth={2} />
          <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-amber-500" />
        </button>

        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded bg-gradient-to-br from-amber-500 to-amber-700 flex items-center justify-center font-display font-bold text-neutral-950">
            RC
          </div>
          <div className="hidden xl:flex flex-col leading-tight">
            <div className="text-xs text-neutral-200 font-medium">Ryan C.</div>
            <div className="mono text-[10px] text-neutral-500 uppercase tracking-widest">
              Operator
            </div>
          </div>
        </div>

        {right}
      </div>

      <div className="lg:hidden px-4 pb-3">
        <div className="font-display text-2xl font-bold text-neutral-100 tracking-tight">
          {pageTitle}
        </div>
        {subtitle ? (
          <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mt-0.5">
            {subtitle}
          </div>
        ) : null}
      </div>
    </header>
  );
};

export default TopHeader;
