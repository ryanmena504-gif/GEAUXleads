import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import TopHeader from "@/components/TopHeader";
import OpportunityRow from "@/components/OpportunityRow";
import { PriorityBand, PriorityScore } from "@/components/PriorityBadge";
import StatusBadge from "@/components/StatusBadge";
import MissionBadge from "@/components/MissionBadge";
import { api } from "@/lib/api";
import { MISSIONS, STATUSES, BANDS, SOURCES, PROJECT_TYPES } from "@/lib/constants";
import { fmtMoney, sourceLabel } from "@/lib/formatters";
import { LayoutGrid, Rows3, X } from "lucide-react";

const FilterChip = ({ label, active, onClick, testId }) => (
  <button
    type="button"
    onClick={onClick}
    data-testid={testId}
    className={
      "mono text-[10px] uppercase tracking-widest px-2.5 py-1 rounded border transition-colors duration-150 " +
      (active
        ? "bg-amber-500/15 border-amber-500/40 text-amber-300"
        : "bh-hairline text-neutral-400 hover:text-neutral-200 hover:bg-white/[0.03]")
    }
  >
    {label}
  </button>
);

const FilterGroup = ({ title, children }) => (
  <div>
    <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-1.5">
      {title}
    </div>
    <div className="flex flex-wrap gap-1.5">{children}</div>
  </div>
);

const Opportunities = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = useState([]);
  const [view, setView] = useState("list");
  const [minScore, setMinScore] = useState(
    Number(searchParams.get("min_score") || 0),
  );
  const [q, setQ] = useState(searchParams.get("q") || "");

  const filters = {
    source: searchParams.get("source") || undefined,
    status: searchParams.get("status") || undefined,
    priority_band: searchParams.get("priority_band") || undefined,
    daily_mission: searchParams.get("daily_mission") || undefined,
    project_type: searchParams.get("project_type") || undefined,
    min_score: minScore || undefined,
    q: q || undefined,
  };

  const setFilter = (key, value) => {
    const next = new URLSearchParams(searchParams);
    if (!value || next.get(key) === value) {
      next.delete(key);
    } else {
      next.set(key, value);
    }
    setSearchParams(next);
  };

  useEffect(() => {
    api.listOpportunities(filters).then(setItems);
    // filters is derived from searchParams/minScore/q; safe to depend on those
     
  }, [searchParams, minScore, q]);

  const activeFilterCount = useMemo(
    () =>
      ["source", "status", "priority_band", "daily_mission", "project_type"].filter(
        (k) => searchParams.get(k),
      ).length + (minScore ? 1 : 0) + (q ? 1 : 0),
    [searchParams, minScore, q],
  );

  const clearAll = () => {
    setSearchParams(new URLSearchParams());
    setMinScore(0);
    setQ("");
  };

  return (
    <>
      <TopHeader
        pageTitle="Opportunities"
        subtitle={`${items.length} matching · ${activeFilterCount} filters`}
      />

      <div className="px-4 lg:px-8 py-6 space-y-5">
        {/* Toolbar */}
        <div className="bh-surface rounded p-4 space-y-4">
          <div className="flex items-center gap-3 flex-wrap">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search name, address, permit, decision maker…"
              data-testid="opps-search"
              className="flex-1 min-w-[220px] bg-transparent border bh-hairline rounded h-9 px-3 text-sm text-neutral-100 placeholder:text-neutral-600 focus:border-amber-500/50 outline-none"
            />
            <div className="inline-flex items-center border bh-hairline rounded overflow-hidden">
              <button
                onClick={() => setView("list")}
                data-testid="view-list"
                className={
                  "px-3 h-9 text-xs inline-flex items-center gap-1.5 transition-colors duration-150 " +
                  (view === "list"
                    ? "bg-white/[0.05] text-neutral-100"
                    : "text-neutral-500 hover:text-neutral-200")
                }
              >
                <Rows3 size={13} /> List
              </button>
              <button
                onClick={() => setView("grid")}
                data-testid="view-grid"
                className={
                  "px-3 h-9 text-xs inline-flex items-center gap-1.5 transition-colors duration-150 " +
                  (view === "grid"
                    ? "bg-white/[0.05] text-neutral-100"
                    : "text-neutral-500 hover:text-neutral-200")
                }
              >
                <LayoutGrid size={13} /> Cards
              </button>
            </div>
            {activeFilterCount > 0 && (
              <button
                onClick={clearAll}
                data-testid="clear-filters"
                className="text-xs text-neutral-400 hover:text-amber-400 inline-flex items-center gap-1"
              >
                <X size={12} /> Clear ({activeFilterCount})
              </button>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            <FilterGroup title="Source">
              {SOURCES.map((s) => (
                <FilterChip
                  key={s}
                  testId={`filter-source-${s}`}
                  label={sourceLabel(s)}
                  active={filters.source === s}
                  onClick={() => setFilter("source", s)}
                />
              ))}
            </FilterGroup>

            <FilterGroup title="Status">
              {STATUSES.map((s) => (
                <FilterChip
                  key={s}
                  testId={`filter-status-${s}`}
                  label={s}
                  active={filters.status === s}
                  onClick={() => setFilter("status", s)}
                />
              ))}
            </FilterGroup>

            <FilterGroup title="Priority Band">
              {BANDS.map((b) => (
                <FilterChip
                  key={b}
                  testId={`filter-band-${b}`}
                  label={`Band ${b}`}
                  active={filters.priority_band === b}
                  onClick={() => setFilter("priority_band", b)}
                />
              ))}
            </FilterGroup>

            <FilterGroup title="Daily Mission">
              {MISSIONS.map((m) => (
                <FilterChip
                  key={m}
                  testId={`filter-mission-${m}`}
                  label={m}
                  active={filters.daily_mission === m}
                  onClick={() => setFilter("daily_mission", m)}
                />
              ))}
            </FilterGroup>

            <FilterGroup title="Project Type">
              {PROJECT_TYPES.map((p) => (
                <FilterChip
                  key={p}
                  testId={`filter-type-${p}`}
                  label={p}
                  active={filters.project_type === p}
                  onClick={() => setFilter("project_type", p)}
                />
              ))}
            </FilterGroup>

            <div>
              <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 mb-1.5">
                Minimum Priority Score
              </div>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={minScore}
                  onChange={(e) => setMinScore(Number(e.target.value))}
                  data-testid="filter-min-score"
                  className="flex-1 accent-amber-500"
                />
                <div className="mono text-sm text-neutral-100 w-10 text-right tabular-nums">
                  {minScore}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Results */}
        {items.length === 0 ? (
          <div className="bh-surface rounded p-12 text-center text-neutral-500 text-sm">
            No opportunities match your filters.
          </div>
        ) : view === "list" ? (
          <div className="space-y-2">
            {items.map((o) => (
              <OpportunityRow key={o.id} opp={o} />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {items.map((o) => (
              <Link
                key={o.id}
                to={`/opportunities/${o.id}`}
                data-testid={`opp-card-${o.id}`}
                className="bh-surface rounded p-4 hover:bg-white/[0.03] transition-colors duration-150 flex flex-col"
              >
                <div className="flex items-start justify-between gap-2">
                  <PriorityScore
                    score={o.priority_score}
                    band={o.priority_band}
                    size="md"
                  />
                  <PriorityBand band={o.priority_band} />
                </div>
                <div className="mt-3 font-display font-semibold text-neutral-100 leading-tight">
                  {o.name}
                </div>
                <div className="mt-1 text-xs text-neutral-500 truncate">
                  {o.project_address}
                </div>
                <div className="mt-3 text-[13px] text-amber-200/90 line-clamp-2">
                  → {o.next_best_action}
                </div>
                <div className="mt-auto pt-4 flex items-center flex-wrap gap-1.5">
                  <MissionBadge mission={o.daily_mission} size="sm" />
                  <StatusBadge status={o.status} />
                </div>
                <div className="mt-3 flex items-center justify-between text-xs">
                  <span className="mono text-[10px] text-neutral-500 uppercase tracking-widest">
                    {sourceLabel(o.source)}
                  </span>
                  <span className="font-display font-semibold text-neutral-200">
                    {fmtMoney(o.estimated_value)}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </>
  );
};

export default Opportunities;
