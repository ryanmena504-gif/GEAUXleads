import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  Printer,
  Home,
  MapPin,
  CheckSquare,
  Square,
  FileText,
} from "lucide-react";
import { api } from "@/lib/api";
import DiscoveryNav from "@/components/DiscoveryNav";

/**
 * DiscoveryLandlords — 63 STR-license owners with no phone/email yet.
 * Ryan's play here is mail-only: select a batch, tap "Print letters",
 * and the app opens a print-optimized page where each landlord's letter
 * is a page break so browser Cmd+P produces one letter per page
 * (physical or PDF).
 */

const STATUS_TABS = [
  { key: "not_contacted", label: "Not contacted" },
  { key: "contacted", label: "Contacted" },
  { key: "all", label: "All" },
];

const normalize = (s) => (s || "").toString().trim().toLowerCase();

const CheckboxRow = ({ item, checked, onToggle }) => (
  <button
    type="button"
    onClick={onToggle}
    data-testid={`landlord-row-${item.id}`}
    data-checked={checked ? "true" : "false"}
    className="w-full text-left bh-surface rounded-md p-4 flex items-start gap-3 hover:shadow-sm transition-shadow"
    style={{
      border: "1px solid var(--bh-hair)",
      background: checked ? "var(--bh-brass-mute)" : "var(--bh-surface)",
      borderColor: checked ? "var(--bh-hair-warm)" : "var(--bh-hair)",
    }}
  >
    <div className="pt-0.5 shrink-0">
      {checked ? (
        <CheckSquare size={16} className="text-[var(--bh-brass)]" strokeWidth={2} />
      ) : (
        <Square size={16} className="text-[var(--bh-ink-mute)]" strokeWidth={1.75} />
      )}
    </div>
    <div className="min-w-0 flex-1">
      <div className="flex items-center gap-2 flex-wrap">
        <Home size={12} className="text-[var(--bh-brass)] shrink-0" />
        <div
          className="font-display text-[15px] font-semibold text-[var(--bh-ink)] truncate"
          data-testid={`landlord-name-${item.id}`}
        >
          {item.owner_name || "Unknown owner"}
        </div>
      </div>
      {item.property_address && (
        <div className="mt-0.5 text-[12px] text-[var(--bh-ink-3)] inline-flex items-center gap-1 truncate">
          <MapPin size={10} strokeWidth={1.75} /> {item.property_address}
        </div>
      )}
      <div className="mt-1 flex items-center gap-2 flex-wrap text-[10.5px] text-[var(--bh-ink-mute)] tabular-nums">
        {item.license_number && <span>{item.license_number}</span>}
        {item.license_expiration && <span>· expires {item.license_expiration}</span>}
        {item.outreach_status && normalize(item.outreach_status) !== "not contacted" && (
          <span className="text-[var(--bh-olive)]">· {item.outreach_status}</span>
        )}
      </div>
    </div>
  </button>
);

const DiscoveryLandlords = () => {
  const [status, setStatus] = useState("not_contacted");
  const [state, setState] = useState({ loading: true, items: [], counts: {} });
  const [selected, setSelected] = useState(new Set());

  useEffect(() => {
    let mounted = true;
    setState((s) => ({ ...s, loading: true }));
    api.discoveryLandlords({ status })
      .then((r) => {
        if (!mounted) return;
        setState({
          loading: false,
          items: r?.items || [],
          counts: r?.status_counts || {},
        });
        // Clear selection when filter changes to avoid confusion.
        setSelected(new Set());
      })
      .catch(() => mounted && setState({ loading: false, items: [], counts: {} }));
    return () => { mounted = false; };
  }, [status]);

  const toggle = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const allSelected = state.items.length > 0 && selected.size === state.items.length;
  const toggleAll = () => {
    if (allSelected) setSelected(new Set());
    else setSelected(new Set(state.items.map((i) => i.id)));
  };

  const printHref = useMemo(() => {
    if (selected.size === 0) return null;
    const ids = Array.from(selected).join(",");
    return `/discovery/landlords/print?ids=${encodeURIComponent(ids)}`;
  }, [selected]);

  const printAllHref = useMemo(() => {
    if (state.items.length === 0) return null;
    const ids = state.items.map((i) => i.id).join(",");
    return `/discovery/landlords/print?ids=${encodeURIComponent(ids)}`;
  }, [state.items]);

  return (
    <div className="px-4 lg:px-8 py-6" data-testid="discovery-landlords-page">
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-[12px] text-[var(--bh-ink-mute)] hover:text-[var(--bh-ink)] mb-4"
      >
        <ArrowLeft size={13} /> Home
      </Link>

      <DiscoveryNav />

      <div className="mono text-[10px] uppercase tracking-widest text-[var(--bh-brass)]">
        Discovery · Landlords
      </div>
      <h1
        className="mt-1 font-display text-[28px] font-bold text-[var(--bh-ink)] tracking-tight"
        data-testid="discovery-landlords-headline"
      >
        Commercial STR license owners
      </h1>
      <p className="mt-1 text-[13px] text-[var(--bh-ink-3)] max-w-3xl">
        {state.counts.all || 63} property owners from the New Orleans
        Commercial Short-Term Rental license registry. No phone or email yet
        — pick a batch and Bloodhound prints them as USPS-ready letters.
        Every letter is a page break, so Cmd+P produces one letter per page.
      </p>

      {/* Status tabs + action bar */}
      <div className="mt-5 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-1.5 flex-wrap" data-testid="discovery-landlords-tabs">
          {STATUS_TABS.map((tab) => {
            const n = state.counts?.[tab.key] ?? 0;
            const active = status === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => setStatus(tab.key)}
                data-testid={`discovery-landlords-tab-${tab.key}`}
                className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md text-[11.5px] font-medium border transition-colors"
                style={{
                  background: active ? "var(--bh-brass)" : "var(--bh-surface)",
                  color: active ? "var(--bh-surface)" : "var(--bh-ink-2)",
                  borderColor: active ? "var(--bh-brass)" : "var(--bh-hair-strong)",
                }}
              >
                {tab.label} <span className="tabular-nums opacity-70">{n}</span>
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {state.items.length > 0 && (
            <button
              type="button"
              onClick={toggleAll}
              data-testid="landlords-toggle-all"
              className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md text-[11.5px] font-medium border"
              style={{
                background: "var(--bh-surface)",
                color: "var(--bh-ink-2)",
                borderColor: "var(--bh-hair-strong)",
              }}
            >
              {allSelected ? "Clear selection" : "Select all"}
            </button>
          )}
          {printHref && (
            <a
              href={printHref}
              target="_blank"
              rel="noopener noreferrer"
              data-testid="landlords-print-selected"
              className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md text-[11.5px] font-semibold border"
              style={{
                background: "var(--bh-brass)",
                color: "var(--bh-surface)",
                borderColor: "var(--bh-brass)",
              }}
            >
              <Printer size={12} strokeWidth={2} />
              Print {selected.size} letter{selected.size === 1 ? "" : "s"}
            </a>
          )}
          {!printHref && printAllHref && (
            <a
              href={printAllHref}
              target="_blank"
              rel="noopener noreferrer"
              data-testid="landlords-print-all"
              className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md text-[11.5px] font-semibold border"
              style={{
                background: "var(--bh-surface)",
                color: "var(--bh-ink-2)",
                borderColor: "var(--bh-hair-strong)",
              }}
            >
              <FileText size={12} strokeWidth={2} />
              Preview all letters
            </a>
          )}
        </div>
      </div>

      {/* List */}
      {state.loading ? (
        <div className="mt-6 text-[13px] text-[var(--bh-ink-3)]">Loading landlord queue…</div>
      ) : state.items.length === 0 ? (
        <div
          className="mt-6 bh-surface rounded-md p-6 text-[13px] text-[var(--bh-ink-3)] text-center"
          data-testid="discovery-landlords-empty"
        >
          No landlords match this filter.
        </div>
      ) : (
        <div className="mt-5 space-y-2">
          {state.items.map((item) => (
            <CheckboxRow
              key={item.id}
              item={item}
              checked={selected.has(item.id)}
              onToggle={() => toggle(item.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default DiscoveryLandlords;
