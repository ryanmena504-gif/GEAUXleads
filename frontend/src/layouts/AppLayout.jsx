import React, { createContext, useContext, useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import Sidebar from "@/components/Sidebar";
import BottomNav from "@/components/BottomNav";
import CommandPalette from "@/components/CommandPalette";
import RouteErrorBoundary from "@/components/RouteErrorBoundary";

const PaletteContext = createContext({ open: () => {} });
export const useCommandPalette = () => useContext(PaletteContext);

const AppLayout = () => {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <PaletteContext.Provider value={{ open: () => setOpen(true) }}>
      <div className="min-h-screen bg-[color:var(--bh-bg)] text-neutral-100">
        <Sidebar />
        <main
          data-testid="app-main"
          className="lg:pl-64 min-h-screen pb-24 lg:pb-0"
        >
          <RouteErrorBoundary key={pathname}>
            <Outlet />
          </RouteErrorBoundary>
        </main>
        <BottomNav />
        <CommandPalette open={open} onOpenChange={setOpen} />
      </div>
    </PaletteContext.Provider>
  );
};

export default AppLayout;
