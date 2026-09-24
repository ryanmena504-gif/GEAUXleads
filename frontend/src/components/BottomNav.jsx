import React, { useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import clsx from "clsx";
import {
  Home,
  Crosshair,
  Compass,
  MoreHorizontal,
  Building2,
  Users,
  Mail,
  TrendingUp,
  Bug,
  Sliders,
  Search,
} from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
  SheetClose,
} from "@/components/ui/sheet";

// Primary bottom-nav slots (max 4 — anything else lives in the "More" sheet).
const primary = [
  { to: "/", label: "Home", icon: Home, end: true },
  { to: "/opportunities", label: "Projects", icon: Crosshair },
  {
    to: "/discovery/property-managers",
    label: "Discovery",
    icon: Compass,
    // Highlight the Discovery tab for ANY /discovery/* sub-route.
    matchPrefix: "/discovery",
  },
];

// Secondary routes that fold into the "More" sheet.
const moreSections = [
  {
    heading: "Discovery Feeds",
    items: [
      {
        to: "/discovery/property-managers",
        label: "Property Managers",
        icon: Building2,
      },
      {
        to: "/discovery/real-estate-agents",
        label: "Real Estate Agents",
        icon: Users,
      },
      { to: "/discovery/landlords", label: "Landlords", icon: Mail },
      { to: "/discovery/investors", label: "Investors", icon: TrendingUp },
    ],
  },
  {
    heading: "Tools",
    items: [
      { to: "/lookup", label: "Phone Lookup", icon: Search },
      { to: "/debug", label: "Debug Panel", icon: Bug },
    ],
  },
  {
    heading: "Preferences",
    items: [{ to: "/settings", label: "Settings", icon: Sliders }],
  },
];

const isPrimaryActive = (item, pathname) => {
  if (item.matchPrefix) return pathname.startsWith(item.matchPrefix);
  if (item.end) return pathname === item.to;
  return pathname === item.to || pathname.startsWith(item.to + "/");
};

export const BottomNav = () => {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  const navigate = useNavigate();

  return (
    <nav
      data-testid="bottom-nav"
      className="lg:hidden fixed bottom-0 inset-x-0 z-30 bh-surface border-t bh-hairline"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <div className="grid grid-cols-4">
        {primary.map((item) => {
          const active = isPrimaryActive(item, pathname);
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              data-testid={`bottomnav-${item.label.toLowerCase()}`}
              className={clsx(
                "flex flex-col items-center justify-center gap-1 py-2.5",
                "text-[10px] transition-colors duration-150",
                active
                  ? "text-amber-400"
                  : "text-neutral-500 hover:text-neutral-200",
              )}
            >
              <item.icon size={18} strokeWidth={2} />
              <span className="tracking-wide">{item.label}</span>
            </NavLink>
          );
        })}

        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <button
              type="button"
              data-testid="bottomnav-more"
              className={clsx(
                "flex flex-col items-center justify-center gap-1 py-2.5",
                "text-[10px] transition-colors duration-150",
                open
                  ? "text-amber-400"
                  : "text-neutral-500 hover:text-neutral-200",
              )}
            >
              <MoreHorizontal size={18} strokeWidth={2} />
              <span className="tracking-wide">More</span>
            </button>
          </SheetTrigger>
          <SheetContent
            side="bottom"
            data-testid="bottomnav-more-sheet"
            className="bh-surface border-t bh-hairline text-neutral-100 p-0 max-h-[80vh] overflow-y-auto"
            style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
          >
            <SheetHeader className="px-5 pt-5 pb-3 border-b bh-hairline text-left">
              <SheetTitle className="text-[13px] font-semibold tracking-tight text-neutral-100">
                Menu
              </SheetTitle>
            </SheetHeader>

            <div className="py-2">
              {moreSections.map((section) => (
                <div key={section.heading} className="py-2">
                  <div className="px-5 py-1.5 text-[10px] uppercase tracking-[0.14em] text-neutral-500">
                    {section.heading}
                  </div>
                  <div className="flex flex-col">
                    {section.items.map((it) => {
                      const active =
                        pathname === it.to ||
                        pathname.startsWith(it.to + "/");
                      return (
                        <SheetClose asChild key={it.to}>
                          <button
                            type="button"
                            data-testid={`more-link-${it.label
                              .toLowerCase()
                              .replace(/[^a-z]+/g, "-")}`}
                            onClick={() => {
                              setOpen(false);
                              navigate(it.to);
                            }}
                            className={clsx(
                              "flex items-center gap-3 px-5 py-3 text-[14px] transition-colors text-left",
                              active
                                ? "bg-[var(--bh-surface-2)] text-amber-400"
                                : "text-neutral-200 hover:bg-[var(--bh-surface-2)]/70",
                            )}
                          >
                            <it.icon size={16} strokeWidth={1.75} />
                            <span className="flex-1 font-medium tracking-tight">
                              {it.label}
                            </span>
                          </button>
                        </SheetClose>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </SheetContent>
        </Sheet>
      </div>
    </nav>
  );
};

export default BottomNav;
