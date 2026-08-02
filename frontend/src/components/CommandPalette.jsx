import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { api } from "@/lib/api";
import {
  LayoutDashboard,
  Crosshair,
  Target,
  Network,
  Radar,
  Settings as SettingsIcon,
  MapPin,
  Phone,
  FileText,
} from "lucide-react";
import { fmtMoney, sourceLabel } from "@/lib/formatters";

const PAGES = [
  { to: "/", label: "Command Center", icon: LayoutDashboard, hint: "Dashboard" },
  { to: "/opportunities", label: "Opportunities", icon: Crosshair, hint: "All records" },
  { to: "/missions", label: "Today's Missions", icon: Target, hint: "Daily plan" },
  { to: "/relationships", label: "Relationships", icon: Network, hint: "Preview — no live data" },
  { to: "/intelligence", label: "Intelligence", icon: Radar, hint: "Preview — no live data" },
  { to: "/settings", label: "Settings", icon: SettingsIcon, hint: "Configuration" },
];

const QUICK_FILTERS = [
  { to: "/opportunities?priority_band=A", label: "Show Band A opportunities" },
  { to: "/opportunities?status=Ready", label: "Show Ready-to-contact" },
  { to: "/opportunities?daily_mission=Call%20Today", label: "Show Call-Today missions" },
  { to: "/opportunities?status=Estimate%20sent", label: "Show Estimates sent" },
  { to: "/opportunities?status=Needs%20research", label: "Show Needs-research" },
];

export const CommandPalette = ({ open, onOpenChange }) => {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [opps, setOpps] = useState([]);

  useEffect(() => {
    if (!open) return;
    // load top opportunities on open; filter client-side by q
    api.listOpportunities().then(setOpps).catch(() => setOpps([]));
  }, [open]);

  const filtered = useMemo(() => {
    const list = opps || [];
    if (!q.trim()) return list.slice(0, 8);
    const ql = q.toLowerCase();
    return list
      .filter((o) => {
        const blob = [
          o.name,
          o.opportunity_id,
          o.project_address,
          o.decision_maker,
          o.permit_number,
          o.project_type,
          o.source,
          o.status,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return blob.includes(ql);
      })
      .slice(0, 12);
  }, [opps, q]);

  const go = (to) => {
    onOpenChange(false);
    setQ("");
    navigate(to);
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput
        value={q}
        onValueChange={setQ}
        placeholder="Search opportunities, addresses, permits, or jump to a page…"
        data-testid="palette-input"
      />
      <CommandList data-testid="palette-list">
        <CommandEmpty>No matches found.</CommandEmpty>

        {filtered.length > 0 && (
          <CommandGroup heading="Opportunities">
            {filtered.map((o) => (
              <CommandItem
                key={o.id}
                value={`${o.name} ${o.project_address || ""} ${o.permit_number || ""} ${o.decision_maker || ""}`}
                onSelect={() => go(`/opportunities/${o.id}`)}
                data-testid={`palette-opp-${o.id}`}
              >
                <div className="flex items-center gap-3 w-full">
                  <div className="mono text-[10px] text-neutral-500 min-w-[36px] tabular-nums">
                    {o.priority_score ?? "—"}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="truncate text-sm text-neutral-100">
                      {o.name}
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 text-[11px] text-neutral-500">
                      {o.project_address && (
                        <span className="inline-flex items-center gap-1 truncate">
                          <MapPin size={10} /> {o.project_address}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="mono text-[10px] text-neutral-500 uppercase tracking-widest whitespace-nowrap">
                    {sourceLabel(o.source)}
                  </div>
                  <div className="font-display text-sm text-neutral-200 whitespace-nowrap">
                    {fmtMoney(o.estimated_value)}
                  </div>
                </div>
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        <CommandSeparator />

        <CommandGroup heading="Quick filters">
          {QUICK_FILTERS.map((f) => (
            <CommandItem
              key={f.to}
              value={f.label}
              onSelect={() => go(f.to)}
              data-testid={`palette-filter-${f.label}`}
            >
              <FileText size={13} className="text-amber-400 mr-2" />
              <span className="text-sm">{f.label}</span>
            </CommandItem>
          ))}
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Pages">
          {PAGES.map((p) => (
            <CommandItem
              key={p.to}
              value={`${p.label} ${p.hint}`}
              onSelect={() => go(p.to)}
              data-testid={`palette-page-${p.label}`}
            >
              <p.icon size={13} className="text-neutral-400 mr-2" />
              <span className="text-sm flex-1">{p.label}</span>
              <span className="mono text-[10px] text-neutral-500 uppercase tracking-widest">
                {p.hint}
              </span>
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
};

export default CommandPalette;
