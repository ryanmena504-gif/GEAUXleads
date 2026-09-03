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
  Search,
  X,
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
  const [query, setQuery] = useState("");

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
        setQuery("");
      })
      .catch(() => mounted && setState({ loading: false, items: [], counts: {} }));
    return () => { mounted = false; };
  }, [status]);

  // ZIP extractor pulled from the free-text property_address (regex-only —
  // Airtable has no ZIP field on this table). Falls back to null so
  // landlords without a ZIP still show up under "unspecified".
  const zipFromAddress = (addr) => {
    if (!addr) return null;
    const m = addr.match(/\b(\d{5})(?:-\d{4})?\b/);
    return m ? m[1] : null;
  };

  // Distinct ZIPs across the current status set (with counts) for the
  // pill-style batch filter.
  const zipBuckets = useMemo(() => {
    const buckets = new Map();
    for (const item of state.items) {
      const zip = zipFromAddress(item.property_address);
      const key = zip || "no_zip";
      buckets.set(key, (buckets.get(key) || 0) + 1);
    }
    return Array.from(buckets.entries())
      .sort((a, b) => {
        // Real ZIPs first, "no_zip" last.
        if (a[0] === "no_zip") return 1;
        if (b[0] === "no_zip") return -1;
        return a[0].localeCompare(b[0]);
      });
  }, [state.items]);

  // Filter chain: apply free-text query first (matches owner name, address,
  // license number, ZIP), then narrow further via nothing else — one field
  // is enough because the query is already treated as a substring match.
  const filteredItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return state.items;
    return state.items.filter((item) => {
      const haystack = [
        item.owner_name,
        item.property_address,
        item.mailing_address,
        item.license_number,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [state.items, query]);

  const toggle = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Select-all applies to the CURRENT filtered set so Ryan can search for
  // "70115" then hit Select all → print only that ZIP.
  const filteredIds = useMemo(() => filteredItems.map((i) => i.id), [filteredItems]);
  const allFilteredSelected =
    filteredIds.length > 0 && filteredIds.every((id) => selected.has(id));
  const toggleAll = () => {
    if (allFilteredSelected) {
      // Clear only the filtered subset — keep any out-of-filter selections.
      setSelected((prev) => {
        const next = new Set(prev);
        for (const id of filteredIds) next.delete(id);
        return next;
      });
    } else {
      setSelected((prev) => {
        const next = new Set(prev);
        for (const id of filteredIds) next.add(id);
        return next;
      });
    }
  };

  const printHref = useMemo(() => {
    if (selected.size === 0) return null;
    const ids = Array.from(selected).join(",");
    return `/discovery/landlords/print?ids=${encodeURIComponent(ids)}`;
  }, [selected]);

  const printAllHref = useMemo(() => {
    if (filteredItems.length === 0) return null;
    const ids = filteredItems.map((i) => i.id).join(",");
    return `/discovery/landlords/print?ids=${encodeURIComponent(ids)}`;
  }, [filteredItems]);

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

      {/* Search + ZIP quick-filter row */}
      <div
        className="mt-5 bh-surface rounded-md p-3 border bh-hairline space-y-2.5"
        data-testid="landlords-filter-bar"
      >
        <div className="relative">
          <Search
            size={13}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--bh-ink-mute)] pointer-events-none"
          />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search ZIP, address, owner, or license #"
            data-testid="landlords-search-input"
            className="w-full h-9 pl-9 pr-9 rounded-md text-[12.5px] bg-transparent border bh-hairline focus:border-[var(--bh-brass)]/60 outline-none text-[var(--bh-ink)]"
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery("")}
              data-testid="landlords-search-clear"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--bh-ink-mute)] hover:text-[var(--bh-ink)]"
            >
              <X size={13} />
            </button>
          )}
        </div>
        {zipBuckets.length > 1 && (
          <div className="flex items-center gap-1.5 flex-wrap" data-testid="landlords-zip-buckets">
            <span className="mono text-[9.5px] uppercase tracking-widest text-[var(--bh-ink-mute)] mr-1">
              ZIP:
            </span>
            <button
              type="button"
              onClick={() => setQuery("")}
              data-testid="landlords-zip-all"
              className="inline-flex items-center gap-1 h-6 px-2 rounded text-[10.5px] font-medium border"
              style={{
                background: !query ? "var(--bh-brass)" : "var(--bh-surface)",
                color: !query ? "var(--bh-surface)" : "var(--bh-ink-2)",
                borderColor: !query ? "var(--bh-brass)" : "var(--bh-hair-strong)",
              }}
            >
              All <span className="opacity-70 tabular-nums">{state.items.length}</span>
            </button>
            {zipBuckets.map(([zip, count]) => {
              const label = zip === "no_zip" ? "No ZIP" : zip;
              const active = query.trim() === (zip === "no_zip" ? "" : zip);
              return (
                <button
                  key={zip}
                  type="button"
                  onClick={() => setQuery(zip === "no_zip" ? "" : zip)}
                  data-testid={`landlords-zip-${zip}`}
                  disabled={zip === "no_zip"}
                  className="inline-flex items-center gap-1 h-6 px-2 rounded text-[10.5px] font-medium border tabular-nums"
                  style={{
                    background: active ? "var(--bh-brass)" : "var(--bh-surface)",
                    color: active ? "var(--bh-surface)" : "var(--bh-ink-2)",
                    borderColor: active ? "var(--bh-brass)" : "var(--bh-hair-strong)",
                    opacity: zip === "no_zip" ? 0.5 : 1,
                    cursor: zip === "no_zip" ? "not-allowed" : "pointer",
                  }}
                >
                  {label} <span className="opacity-70">{count}</span>
                </button>
              );
            })}
          </div>
        )}
        <div className="text-[11px] text-[var(--bh-ink-mute)] tabular-nums">
          Showing <strong className="text-[var(--bh-ink-2)]">{filteredItems.length}</strong> of {state.items.length} {status.replace(/_/g, " ")} · {selected.size} selected
        </div>
      </div>

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
          {filteredItems.length > 0 && (
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
              {allFilteredSelected ? "Clear selection" : `Select all ${filteredItems.length}`}
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
              Preview {filteredItems.length} letters
            </a>
          )}
        </div>
      </div>

      {/* List */}
      {state.loading ? (
        <div className="mt-6 text-[13px] text-[var(--bh-ink-3)]">Loading landlord queue…</div>
      ) : filteredItems.length === 0 ? (
        <div
          className="mt-6 bh-surface rounded-md p-6 text-[13px] text-[var(--bh-ink-3)] text-center"
          data-testid="discovery-landlords-empty"
        >
          {query
            ? `No landlords match "${query}". Try a different ZIP or keyword.`
            : "No landlords match this filter."}
        </div>
      ) : (
        <div className="mt-5 space-y-2">
          {filteredItems.map((item) => (
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
