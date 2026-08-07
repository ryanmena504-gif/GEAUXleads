import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import TopHeader from "@/components/TopHeader";
import MetricCard from "@/components/MetricCard";
import OpportunityRow from "@/components/OpportunityRow";
import StatusPipeline from "@/components/StatusPipeline";
import { PriorityBand, PriorityScore } from "@/components/PriorityBadge";
import MissionBadge from "@/components/MissionBadge";
import NextBestAction from "@/components/NextBestAction";
import { api } from "@/lib/api";
import { fmtMoney, fmtRelative, sourceLabel } from "@/lib/formatters";
import { LANES, LANE_LABEL, MISSIONS } from "@/lib/constants";
import { useLiveUpdates } from "@/hooks/useLiveUpdates";
import LaneBadge from "@/components/LaneBadge";
import {
  Zap,
  Flame,
  PhoneCall,
  SearchCode,
  Landmark,
  Radar,
  ChevronRight,
} from "lucide-react";
import { Link } from "react-router-dom";

const missionCount = (grouped, mission) => (grouped?.[mission] || []).length;

const CommandCenter = () => {
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [missions, setMissions] = useState(null);
  const [pipeline, setPipeline] = useState([]);
  const [top, setTop] = useState([]);
  const [recent, setRecent] = useState([]);
  const [activeMission, setActiveMission] = useState("all");
  const [lanes, setLanes] = useState([]);
  const [topLane, setTopLane] = useState("all");
  const [topByLane, setTopByLane] = useState({});

  const loadAll = useCallback(() => {
    Promise.all([
      api.summary(),
      api.missions(),
      api.pipeline(),
      api.top(6),
      api.recent(6),
      api.laneBreakdown().catch(() => []),
      api.topByLane(5).catch(() => ({})),
    ]).then(([s, m, p, t, r, l, tbl]) => {
      setSummary(s);
      setMissions(m);
      setPipeline(p);
      setTop(t);
      setRecent(r);
      setLanes(l);
      setTopByLane(tbl || {});
    });
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // Push-refresh whenever Airtable fires a webhook (opps + NBA both update).
  useLiveUpdates(useCallback(() => loadAll(), [loadAll]));

  const missionList = useMemo(() => {
    if (!missions) return [];
    if (activeMission === "all") {
      return MISSIONS.flatMap((m) => (missions[m] || []).map((o) => ({ ...o }))).sort(
        (a, b) => (b.priority_score || 0) - (a.priority_score || 0),
      );
    }
    return missions[activeMission] || [];
  }, [missions, activeMission]);

  const goFilter = (params) => {
    const q = new URLSearchParams(params).toString();
    navigate(`/opportunities?${q}`);
  };

  return (
    <>
      <TopHeader
        pageTitle="Today's Work"
        subtitle="The few calls, texts, emails, and follow-ups worth doing today"
      />

      <div className="px-5 lg:px-10 py-8 space-y-10">
        {/* Next Best Action — dominant top section */}
        <NextBestAction />

        {/* Metric row */}
        <section
          data-testid="metric-strip"
          className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4"
        >
          <MetricCard
            testId="metric-new"
            label="New this week"
            value={summary?.new_opportunities ?? "—"}
            hint="Fresh leads to review"
            icon={Zap}
            onClick={() => goFilter({ status: "New" })}
          />
          <MetricCard
            testId="metric-immediate"
            label="Move today"
            value={summary?.immediate_action ?? "—"}
            hint="Call, text, or visit"
            icon={Flame}
            accent
            onClick={() => goFilter({ daily_mission: "Call Today" })}
          />
          <MetricCard
            testId="metric-ready"
            label="Ready to contact"
            value={summary?.ready_to_contact ?? "—"}
            hint="Public phone or email on file"
            icon={PhoneCall}
            tone="olive"
            onClick={() => goFilter({ status: "Ready" })}
          />
          <MetricCard
            testId="metric-research"
            label="Get more info first"
            value={summary?.needs_research ?? "—"}
            hint="One piece of info missing"
            icon={SearchCode}
            tone="sand"
            onClick={() => goFilter({ status: "Needs research" })}
          />
          <MetricCard
            testId="metric-pipeline"
            label="Possible work value"
            value={fmtMoney(summary?.total_pipeline_value ?? 0)}
            hint={`Across ${summary?.active_count ?? 0} active`}
            icon={Landmark}
            tone="brass"
            onClick={() => navigate("/opportunities")}
          />
        </section>

        {/* Lane Breakdown — three parallel funnels */}
        <section
          data-testid="lane-breakdown"
          className="grid grid-cols-1 md:grid-cols-3 gap-3"
        >
          {(lanes.length ? lanes : LANES.map((l) => ({
              lane: l.key, label: l.label, total: 0, active: 0,
              pipeline_value: 0, top_score: null,
            }))).map((row) => (
            <button
              key={row.lane}
              type="button"
              data-testid={`lane-card-${row.lane}`}
              onClick={() => goFilter({ lane: row.lane })}
              className="bh-surface rounded p-4 text-left hover:bg-white/[0.03] transition-colors duration-150 border-t"
              style={{
                borderTopColor:
                  row.lane === "partner" ? "rgba(16,185,129,0.6)"
                  : row.lane === "non_permit" ? "rgba(56,189,248,0.6)"
                  : "rgba(217,119,6,0.6)",
              }}
            >
              <div className="flex items-center gap-2">
                <LaneBadge lane={row.lane} />
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <div className="font-display text-2xl font-bold text-neutral-100 tabular-nums">
                  {row.active}
                </div>
                <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
                  active / {row.total} total
                </div>
              </div>
              <div className="mt-1 mono text-[10px] uppercase tracking-widest text-neutral-500">
                Possible work value · {fmtMoney(row.pipeline_value || 0)}
              </div>
            </button>
          ))}
        </section>

        {/* Today's Missions (dominant) */}
        <section data-testid="section-missions" className="space-y-3">
          <div className="flex items-baseline justify-between gap-3">
            <div>
              <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
                Follow-ups
              </div>
              <h2 className="font-display text-[24px] text-[var(--bh-ink)] tracking-tight">
                Follow-ups for today
              </h2>
            </div>
            <Link
              to="/missions"
              data-testid="missions-see-all"
              className="text-[12px] text-[var(--bh-brass)] hover:text-[var(--bh-brass-2)] inline-flex items-center gap-1"
            >
              Open follow-ups <ChevronRight size={13} strokeWidth={1.75} />
            </Link>
          </div>

          <div className="flex gap-1.5 flex-wrap">
            <button
              onClick={() => setActiveMission("all")}
              data-testid="mission-filter-all"
              className={
                "mono text-[10px] uppercase tracking-widest px-2.5 py-1 rounded border transition-colors duration-150 " +
                (activeMission === "all"
                  ? "bg-amber-500/15 border-amber-500/40 text-amber-300"
                  : "bh-hairline text-neutral-400 hover:text-neutral-200 hover:bg-white/[0.03]")
              }
            >
              All ({missions ? Object.values(missions).flat().length : 0})
            </button>
            {MISSIONS.map((m) => {
              const c = missionCount(missions, m);
              if (c === 0) return null;
              const active = activeMission === m;
              const label = m === "Research First" ? "Get more info first" : m;
              return (
                <button
                  key={m}
                  data-testid={`mission-filter-${m}`}
                  onClick={() => setActiveMission(m)}
                  className={
                    "mono text-[10px] uppercase tracking-widest px-2.5 py-1 rounded border transition-colors duration-150 " +
                    (active
                      ? "bg-amber-500/15 border-amber-500/40 text-amber-300"
                      : "bh-hairline text-neutral-400 hover:text-neutral-200 hover:bg-white/[0.03]")
                  }
                >
                  {label} ({c})
                </button>
              );
            })}
          </div>

          <div className="space-y-2 bh-fade-in">
            {missionList.length === 0 ? (
              <div className="bh-surface rounded p-8 text-center text-neutral-500 text-sm">
                No follow-ups in this bucket.
              </div>
            ) : (
              missionList.slice(0, 8).map((o) => (
                <OpportunityRow key={o.id} opp={o} />
              ))
            )}
          </div>
        </section>

        {/* Top Opportunities + Recent Discoveries */}
        <section className="grid lg:grid-cols-2 gap-6">
          <div>
            <div className="flex items-baseline justify-between mb-3">
              <div>
                <div className="bh-eyebrow">Top picks</div>
                <h2 className="font-display text-[22px] text-[var(--bh-ink)] tracking-tight">
                  Top projects
                </h2>
              </div>
              <Link
                to="/opportunities"
                className="text-[12px] text-[var(--bh-brass)] hover:text-[var(--bh-brass-2)]"
              >
                View all
              </Link>
            </div>
            <div className="flex gap-1.5 flex-wrap mb-3">
              <button
                onClick={() => setTopLane("all")}
                data-testid="top-lane-all"
                className={
                  "mono text-[10px] uppercase tracking-widest px-2.5 py-1 rounded border transition-colors duration-150 " +
                  (topLane === "all"
                    ? "bg-amber-500/15 border-amber-500/40 text-amber-300"
                    : "bh-hairline text-neutral-400 hover:text-neutral-200 hover:bg-white/[0.03]")
                }
              >
                All lanes
              </button>
              {LANES.map((l) => {
                const count = (topByLane[l.key] || []).length;
                if (count === 0 && topLane !== l.key) return null;
                return (
                  <button
                    key={l.key}
                    onClick={() => setTopLane(l.key)}
                    data-testid={`top-lane-${l.key}`}
                    className={
                      "mono text-[10px] uppercase tracking-widest px-2.5 py-1 rounded border transition-colors duration-150 " +
                      (topLane === l.key
                        ? "bg-white/[0.06] border-neutral-500 text-neutral-100"
                        : "bh-hairline text-neutral-400 hover:text-neutral-200 hover:bg-white/[0.03]")
                    }
                  >
                    {l.label} ({count})
                  </button>
                );
              })}
            </div>
            <div className="bh-surface rounded overflow-hidden">
              {(topLane === "all"
                ? top
                : (topByLane[topLane] || [])
              ).map((o, i) => (
                <Link
                  key={o.id}
                  to={`/opportunities/${o.id}`}
                  data-testid={`top-opp-${o.id}`}
                  className="flex items-center gap-3 px-4 py-3 border-b bh-hairline last:border-b-0 hover:bg-white/[0.03] transition-colors duration-150"
                >
                  <div className="mono text-neutral-600 text-sm w-6 tabular-nums">
                    {String(i + 1).padStart(2, "0")}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <div className="truncate font-medium text-neutral-100">
                        {o.name}
                      </div>
                      <LaneBadge lane={o.lane} />
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 text-[11px] text-neutral-500">
                      <span>{sourceLabel(o.source)}</span>
                      <span>·</span>
                      <span className="truncate">{o.project_type}</span>
                    </div>
                    <div className="mt-1 text-[12px] text-amber-200/80 truncate">
                      → {o.next_best_action}
                    </div>
                  </div>
                  <div className="hidden sm:flex flex-col items-end min-w-[80px]">
                    <PriorityScore
                      score={o.priority_score}
                      band={o.priority_band}
                      size="sm"
                    />
                    <PriorityBand band={o.priority_band} className="mt-1" />
                  </div>
                  <div className="hidden md:flex flex-col items-end min-w-[70px]">
                    <div className="mono text-[9px] uppercase tracking-widest text-neutral-500">
                      Est.
                    </div>
                    <div className="font-display font-semibold text-neutral-200 tabular-nums">
                      {fmtMoney(o.estimated_value)}
                    </div>
                  </div>
                </Link>
              ))}
              {(topLane !== "all" && (topByLane[topLane] || []).length === 0) && (
                <div className="px-4 py-6 text-center text-neutral-500 text-sm">
                  No records in this lane yet.
                </div>
              )}
            </div>
          </div>

          <div>
            <div className="flex items-baseline justify-between mb-3">
              <div>
                <div className="mono text-[10px] uppercase tracking-widest text-neutral-500">
                  Just found
                </div>
                <h2 className="font-display text-xl font-bold text-neutral-100">
                  Recent Discoveries
                </h2>
              </div>
              <div className="mono text-[10px] text-neutral-500 uppercase tracking-widest inline-flex items-center gap-1.5">
                <Radar size={12} className="text-amber-400" /> Live
              </div>
            </div>
            <div className="bh-surface rounded overflow-hidden">
              {recent.map((o) => (
                <Link
                  key={o.id}
                  to={`/opportunities/${o.id}`}
                  data-testid={`recent-opp-${o.id}`}
                  className="flex items-start gap-3 px-4 py-3 border-b bh-hairline last:border-b-0 hover:bg-white/[0.03] transition-colors duration-150"
                >
                  <span
                    className="mt-1.5 w-1.5 h-1.5 rounded-full bg-amber-400 bh-pulse-dot shrink-0"
                    aria-hidden
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="mono text-[10px] uppercase tracking-widest text-neutral-500">
                        {sourceLabel(o.source)}
                      </span>
                      <span className="mono text-[10px] text-neutral-600">
                        {fmtRelative(o.created_time)}
                      </span>
                    </div>
                    <div className="mt-1 truncate font-medium text-neutral-100">
                      {o.name}
                    </div>
                    <div className="mt-0.5 text-[11px] text-neutral-500 truncate">
                      {o.project_address}
                    </div>
                    <div className="mt-2">
                      <MissionBadge mission={o.daily_mission} size="sm" />
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </section>

        {/* Pipeline */}
        <section data-testid="section-pipeline" className="space-y-3">
          <div>
            <div className="bh-eyebrow">Where things stand</div>
            <h2 className="font-display text-[22px] text-[var(--bh-ink)] tracking-tight">
              Where every project stands
            </h2>
          </div>
          <StatusPipeline
            stages={pipeline}
            onSelect={(s) => goFilter({ status: s })}
          />
        </section>
      </div>
    </>
  );
};

export default CommandCenter;
