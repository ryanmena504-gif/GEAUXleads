import React from "react";
import { NavLink } from "react-router-dom";
import clsx from "clsx";
import {
  LayoutDashboard,
  Target,
  Crosshair,
  Network,
  Radar,
  Settings as SettingsIcon,
} from "lucide-react";
import BloodhoundLogo from "@/components/BloodhoundLogo";
import LiveRefreshIndicator from "@/components/LiveRefreshIndicator";

const nav = [
  { to: "/", label: "Command Center", icon: LayoutDashboard, code: "CC" },
  { to: "/opportunities", label: "Opportunities", icon: Crosshair, code: "OP" },
  { to: "/missions", label: "Today's Missions", icon: Target, code: "MS" },
  { to: "/relationships", label: "Relationships", icon: Network, code: "RE", preview: true },
  { to: "/intelligence", label: "Intelligence", icon: Radar, code: "IN", preview: true },
  { to: "/settings", label: "Settings", icon: SettingsIcon, code: "SE" },
];

export const Sidebar = () => (
  <aside
    data-testid="sidebar"
    className="hidden lg:flex fixed inset-y-0 left-0 w-60 flex-col bh-surface border-r bh-hairline z-30"
  >
    <div className="px-5 pt-6 pb-4 border-b bh-hairline">
      <BloodhoundLogo />
    </div>

    <nav className="flex-1 px-3 py-5 space-y-0.5">
      {nav.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/"}
          data-testid={`nav-${item.label.toLowerCase().replace(/[^a-z]+/g, "-")}`}
          className={({ isActive }) =>
            clsx(
              "group flex items-center gap-3 px-3 py-2 rounded text-sm transition-colors duration-150",
              isActive
                ? "bg-white/[0.04] text-neutral-100"
                : "text-neutral-400 hover:text-neutral-100 hover:bg-white/[0.03]",
            )
          }
        >
          {({ isActive }) => (
            <>
              <span
                className={clsx(
                  "w-1 h-5 rounded-full transition-colors duration-150",
                  isActive ? "bg-amber-500" : "bg-transparent",
                )}
              />
              <item.icon size={15} strokeWidth={2} />
              <span className="flex-1">{item.label}</span>
              {item.preview ? (
                <span
                  data-testid={`nav-preview-${item.code}`}
                  title="Preview — this section shows no live data"
                  className="mono text-[8px] uppercase tracking-widest px-1.5 py-0.5 rounded border border-amber-500/30 text-amber-400/70"
                >
                  Preview
                </span>
              ) : (
                <span className="mono text-[9px] text-neutral-600 tracking-widest">
                  {item.code}
                </span>
              )}
            </>
          )}
        </NavLink>
      ))}
    </nav>

    <div className="p-4 border-t bh-hairline">
      <LiveRefreshIndicator />
    </div>
  </aside>
);

export default Sidebar;
