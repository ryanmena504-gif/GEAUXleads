import React from "react";
import { NavLink } from "react-router-dom";
import clsx from "clsx";
import { Building2, Users, Mail, TrendingUp } from "lucide-react";

/**
 * DiscoveryNav — top-level tabs on every Discovery page. Keeps the sidebar
 * clean (single "Discovery" entry) while letting operator flip between
 * discovery feeds (Property Managers, Real Estate Agents, Landlords,
 * Investors, …).
 */
const FEEDS = [
  {
    to: "/discovery/property-managers",
    label: "Property Managers",
    icon: Building2,
    testId: "discovery-nav-pm",
  },
  {
    to: "/discovery/real-estate-agents",
    label: "Real Estate Agents",
    icon: Users,
    testId: "discovery-nav-agents",
  },
  {
    to: "/discovery/landlords",
    label: "Landlords",
    icon: Mail,
    testId: "discovery-nav-landlords",
  },
  {
    to: "/discovery/investors",
    label: "Investors",
    icon: TrendingUp,
    testId: "discovery-nav-investors",
  },
];

export const DiscoveryNav = () => (
  <div
    data-testid="discovery-nav"
    className="flex items-center gap-1 border-b bh-hairline pb-3 mb-5 overflow-x-auto"
  >
    {FEEDS.map((f) => (
      <NavLink
        key={f.to}
        to={f.to}
        data-testid={f.testId}
        className={({ isActive }) =>
          clsx(
            "inline-flex items-center gap-1.5 h-8 px-3 rounded-md text-[12px] font-medium border transition-colors whitespace-nowrap",
            isActive
              ? "bg-[var(--bh-brass)] text-[var(--bh-surface)] border-[var(--bh-brass)]"
              : "bg-[var(--bh-surface)] text-[var(--bh-ink-2)] border-[var(--bh-hair-strong)] hover:text-[var(--bh-ink)]",
          )
        }
      >
        <f.icon size={12} strokeWidth={1.75} />
        {f.label}
      </NavLink>
    ))}
  </div>
);

export default DiscoveryNav;
