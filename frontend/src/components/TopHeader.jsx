import React from "react";
import { Bell, Search } from "lucide-react";
import BloodhoundLogo from "@/components/BloodhoundLogo";
import { useCommandPalette } from "@/layouts/AppLayout";

export const TopHeader = ({ pageTitle, subtitle, right }) => {
  const palette = useCommandPalette();
  const now = new Date();
  const dateStr = now.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  return (
    <header
      data-testid="top-header"
      className="sticky top-0 z-20 bh-surface border-b bh-hairline"
      style={{ background: "var(--bh-surface)" }}
    >
      <div className="px-5 lg:px-10 h-[72px] flex items-center gap-5">
        <div className="lg:hidden">
          <BloodhoundLogo compact />
        </div>

        <div className="hidden lg:flex flex-col leading-tight">
          <div className="font-display text-[22px] text-[var(--bh-ink)] tracking-tight">
            {pageTitle}
          </div>
          {subtitle ? (
            <div className="bh-eyebrow mt-0.5">{subtitle}</div>
          ) : null}
        </div>

        <div className="flex-1" />

        <button
          type="button"
          onClick={() => palette.open()}
          data-testid="global-search"
          className="hidden md:flex items-center gap-2 rounded-md px-3 h-10 min-w-[280px] max-w-md text-left transition-colors duration-150"
          style={{
            background: "var(--bh-surface-2)",
            border: "1px solid var(--bh-hair)",
          }}
        >
          <Search size={14} className="text-[var(--bh-ink-mute)]" strokeWidth={1.75} />
          <span className="text-[13px] flex-1 text-[var(--bh-ink-mute)]">
            Search projects, addresses, permits…
          </span>
          <span className="mono text-[10px] text-[var(--bh-ink-mute)] rounded px-1.5 py-0.5 bh-hairline border">
            ⌘K
          </span>
        </button>

        <button
          type="button"
          onClick={() => palette.open()}
          data-testid="mobile-search-btn"
          aria-label="Open search"
          className="md:hidden w-10 h-10 flex items-center justify-center rounded-md bh-surface-2"
        >
          <Search size={16} className="text-[var(--bh-ink-2)]" strokeWidth={1.75} />
        </button>

        <div className="hidden lg:block text-[12px] text-[var(--bh-ink-mute)] tracking-tight">
          {dateStr}
        </div>

        <button
          data-testid="notifications-btn"
          className="relative w-10 h-10 flex items-center justify-center rounded-md bh-surface-2"
          aria-label="Notifications"
        >
          <Bell size={15} className="text-[var(--bh-ink-2)]" strokeWidth={1.75} />
          <span
            className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full"
            style={{ background: "var(--bh-brass)" }}
          />
        </button>

        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center font-display text-[15px]"
            style={{
              background: "var(--bh-surface-3)",
              color: "var(--bh-ink)",
              border: "1px solid var(--bh-hair)",
            }}
            aria-label="Account"
          >
            R
          </div>
          <div className="hidden xl:flex flex-col leading-tight">
            <div className="text-[13px] text-[var(--bh-ink)] font-medium">Ryan</div>
            <div className="text-[11px] text-[var(--bh-ink-mute)]">Account Lead</div>
          </div>
        </div>

        {right}
      </div>

      <div className="lg:hidden px-5 pb-4">
        <div className="font-display text-[26px] text-[var(--bh-ink)] tracking-tight">
          {pageTitle}
        </div>
        {subtitle ? (
          <div className="bh-eyebrow mt-1">{subtitle}</div>
        ) : null}
      </div>
    </header>
  );
};

export default TopHeader;
