import React, { createContext, useContext, useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "@/components/Sidebar";
import BottomNav from "@/components/BottomNav";
import CommandPalette from "@/components/CommandPalette";

const PaletteContext = createContext({ open: () => {} });
export const useCommandPalette = () => useContext(PaletteContext);

const AppLayout = () => {
  const [open, setOpen] = useState(false);

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
          className="lg:pl-60 min-h-screen pb-24 lg:pb-0"
        >
          <Outlet />
        </main>
        <BottomNav />
        <CommandPalette open={open} onOpenChange={setOpen} />
      </div>
    </PaletteContext.Provider>
  );
};

export default AppLayout;
