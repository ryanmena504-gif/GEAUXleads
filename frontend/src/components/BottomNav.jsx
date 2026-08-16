import React from "react";
import { NavLink } from "react-router-dom";
import clsx from "clsx";
import {
  Home,
  Crosshair,
  Sliders,
} from "lucide-react";

const nav = [
  { to: "/", label: "Home", icon: Home },
  { to: "/opportunities", label: "Projects", icon: Crosshair },
  { to: "/settings", label: "Settings", icon: Sliders },
];

export const BottomNav = () => (
  <nav
    data-testid="bottom-nav"
    className="lg:hidden fixed bottom-0 inset-x-0 z-30 bh-surface border-t bh-hairline"
    style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
  >
    <div className="grid grid-cols-3">
      {nav.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/"}
          data-testid={`bottomnav-${item.label.toLowerCase()}`}
          className={({ isActive }) =>
            clsx(
              "flex flex-col items-center justify-center gap-1 py-2.5",
              "text-[10px] transition-colors duration-150",
              isActive
                ? "text-amber-400"
                : "text-neutral-500 hover:text-neutral-200",
            )
          }
        >
          <item.icon size={18} strokeWidth={2} />
          <span className="tracking-wide">{item.label}</span>
        </NavLink>
      ))}
    </div>
  </nav>
);

export default BottomNav;
