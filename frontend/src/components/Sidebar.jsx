import React from "react";
import { NavLink } from "react-router-dom";
import clsx from "clsx";
import {
  Sun,
  FileText,
  Users,
  Sliders,
} from "lucide-react";
import BloodhoundLogo from "@/components/BloodhoundLogo";
import LiveRefreshIndicator from "@/components/LiveRefreshIndicator";

const nav = [
  { to: "/", label: "Today", icon: Sun },
  { to: "/opportunities", label: "All Projects", icon: FileText },
  { to: "/relationships", label: "People to Know", icon: Users },
  { to: "/settings", label: "Settings", icon: Sliders },
];

export const Sidebar = () => {
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
