import React, { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import clsx from "clsx";
import {
  Sun,
  FileText,
  ListChecks,
  Users,
  BookOpen,
  Sliders,
  Inbox,
} from "lucide-react";
import BloodhoundLogo from "@/components/BloodhoundLogo";
import LiveRefreshIndicator from "@/components/LiveRefreshIndicator";
import { api } from "@/lib/api";
import { useLiveUpdates } from "@/hooks/useLiveUpdates";

// Route paths preserved; visible labels rebranded to owner-operated,
// architectural language. No two-letter call signs, no tactical rails.
const nav = [
  { to: "/", label: "Today's Work", icon: Sun },
  { to: "/opportunities", label: "Project List", icon: FileText },
  { to: "/missions", label: "Follow-Ups", icon: ListChecks },
  { to: "/relationships", label: "People to Know", icon: Users },
  { to: "/intelligence", label: "Projects to Watch", icon: BookOpen },
  { to: "/review-queue", label: "Needs a Look", icon: Inbox, showCount: true },
  { to: "/settings", label: "Settings", icon: Sliders },
];

export const Sidebar = () => {
  const [readyCount, setReadyCount] = useState(0);

  const refreshCount = React.useCallback(() => {
    api
      .listDraftQueue("Ready for Ryan review", 1)
      .then((d) => setReadyCount(d?.counts?.["Ready for Ryan review"] || 0))
      .catch(() => {});
  }, []);

  useEffect(() => {
    refreshCount();
    const t = setInterval(refreshCount, 45000);
    return () => clearInterval(t);
  }, [refreshCount]);
  useLiveUpdates(refreshCount);

  return (
    <aside
      data-testid="sidebar"
      className="hidden lg:flex fixed inset-y-0 left-0 w-64 flex-col bh-surface border-r bh-hairline z-30"
      style={{ background: "var(--bh-surface)" }}
    >
      <div className="px-6 pt-7 pb-5 border-b bh-hairline">
        <BloodhoundLogo />
      </div>

      <nav className="flex-1 px-3 py-6 space-y-0.5">
        {nav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            data-testid={`nav-${item.label.toLowerCase().replace(/[^a-z]+/g, "-")}`}
            className={({ isActive }) =>
              clsx(
                "group flex items-center gap-3 px-3 py-2 rounded-md text-[14px] transition-colors duration-150",
                isActive
                  ? "bg-[var(--bh-surface-2)] text-[var(--bh-ink)]"
                  : "text-[var(--bh-ink-3)] hover:text-[var(--bh-ink)] hover:bg-[var(--bh-surface-2)]/70",
              )
            }
          >
            <item.icon size={15} strokeWidth={1.75} />
            <span className="flex-1 font-medium tracking-tight">{item.label}</span>
            {item.showCount && readyCount > 0 && (
              <span
                data-testid="nav-review-queue-count"
                className="text-[10.5px] font-medium tabular-nums px-1.5 py-0.5 rounded-full"
                style={{
                  background: "var(--bh-brass-mute)",
                  color: "var(--bh-brass)",
                  border: "1px solid var(--bh-hair-warm)",
                }}
              >
                {readyCount}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="p-4 border-t bh-hairline">
        <LiveRefreshIndicator />
      </div>
    </aside>
  );
};

export default Sidebar;
