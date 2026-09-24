import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, AlertCircle, CheckCircle2, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";
import LaneBadge from "@/components/LaneBadge";

/**
 * DebugPanel — one-screen view of every governed field on every record.
 *
 * Purpose: when Make hasn't finished classifying a record, its governed
 * fields are null. This screen surfaces those gaps visually so operator
 * (and Claude/Make on the other side) can spot missing governance in
 * one scroll.
 *
 * Zero writes. Every cell is read-only, sourced from `/api/opportunities`.
 * Every row links to the full record for context.
 */

// The 17 governed fields owned by Airtable + Make. This is the authoritative
// contract — never edited from the frontend. Order matches the order in
// airtable_service.py so the columns read the same top-to-bottom as the
// underlying schema.
const GOVERNED_FIELDS = [
  { key: "current_queue", label: "Current Queue", critical: true },
  { key: "contact_readiness", label: "Contact Readiness", critical: true },
  { key: "contact_state", label: "Contact State" },
  { key: "money_signal", label: "Money Signal" },
  { key: "operator_activity", label: "Operator Activity" },
  { key: "premium_fit", label: "Premium Fit" },
  { key: "evidence_status", label: "Evidence Status" },
  { key: "freshness", label: "Freshness" },
  { key: "governed_priority_score", label: "Priority Score", critical: true },
  { key: "score_basis", label: "Score Basis" },
  { key: "priority_explanation", label: "Priority Explanation" },
  { key: "current_recommendation", label: "Current Recommendation" },
  { key: "public_contact_evidence", label: "Public Contact Evidence" },
  { key: "contact_verified_date", label: "Contact Verified Date" },
  { key: "project_fit_reason", label: "Project Fit Reason" },
  { key: "last_classified_at", label: "Last Classified At" },
  { key: "classification_version", label: "Classification Version" },
];

const CRITICAL_KEYS = GOVERNED_FIELDS.filter((f) => f.critical).map((f) => f.key);

const isFilled = (v) =>
  v !== null && v !== undefined && v !== "" && !(typeof v === "number" && isNaN(v));

const trimForCell = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const s = String(v);
  return s.length > 80 ? `${s.slice(0, 77)}…` : s;
};

const Cell = ({ value }) => {
  const filled = isFilled(value);
  const display = trimForCell(value);
  return (
    <td
      className="px-2 py-1.5 align-top border-b bh-hairline text-[11px] leading-snug tabular-nums"
      style={{
        color: filled ? "var(--bh-ink-2)" : "#c94a3b",
        background: filled ? "transparent" : "rgba(201,74,59,0.05)",
      }}
      data-testid={`debug-cell-${filled ? "filled" : "empty"}`}
    >
      {filled ? display : <span className="italic opacity-70">null</span>}
    </td>
  );
};

const LANE_FILTERS = [
  { key: "all", label: "All lanes" },
  { key: "market_capture", label: "Projects" },
  { key: "partner", label: "Partners" },
  { key: "landlord", label: "Landlords" },
  { key: "non_permit", label: "Watching" },
];

const DebugPanel = () => {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [lane, setLane] = useState("all");

  useEffect(() => {
    let mounted = true;
    api
      .listOpportunities()
      .then((r) => mounted && setItems(r || []))
      .catch(() => mounted && setItems([]))
      .finally(() => mounted && setLoading(false));
    return () => { mounted = false; };
  }, []);

  const filtered = useMemo(() => {
    if (lane === "all") return items;
    return items.filter((o) => (o.lane || "").toLowerCase() === lane);
  }, [items, lane]);

  const stats = useMemo(() => {
    const total = filtered.length;
    if (total === 0) return { total: 0, fullyClassified: 0, criticalGaps: 0, anyGaps: 0 };
    let fullyClassified = 0;
    let criticalGaps = 0;
    let anyGaps = 0;
    for (const o of filtered) {
      const filledCount = GOVERNED_FIELDS.filter((f) => isFilled(o[f.key])).length;
      if (filledCount === GOVERNED_FIELDS.length) fullyClassified += 1;
      const critMissing = CRITICAL_KEYS.some((k) => !isFilled(o[k]));
      if (critMissing) criticalGaps += 1;
      const anyMissing = GOVERNED_FIELDS.some((f) => !isFilled(o[f.key]));
      if (anyMissing) anyGaps += 1;
    }
    return { total, fullyClassified, criticalGaps, anyGaps };
  }, [filtered]);

  const laneCounts = useMemo(() => {
    const m = {};
    for (const o of items) {
      const k = (o.lane || "unknown").toLowerCase();
      m[k] = (m[k] || 0) + 1;
    }
    return m;
  }, [items]);

  return (
    <div className="px-4 lg:px-8 py-6" data-testid="debug-panel">
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-[12px] text-[var(--bh-ink-mute)] hover:text-[var(--bh-ink)] mb-4"
      >
        <ArrowLeft size={13} /> Home
      </Link>

      <div className="mono text-[10px] uppercase tracking-widest text-[var(--bh-brass)]">
        Governance debug
      </div>
      <h1
        className="mt-1 font-display text-[28px] font-bold text-[var(--bh-ink)] tracking-tight"
        data-testid="debug-headline"
      >
        Every governed field on every record
      </h1>
      <p className="mt-1 text-[13px] text-[var(--bh-ink-3)] max-w-3xl">
        Bloodhound never invents governed values — this panel shows exactly what
        Airtable + Make have written. Red cells are unset. If a record has red
        cells in the <strong>Queue</strong>, <strong>Readiness</strong>, or{" "}
        <strong>Score</strong> columns, Make hasn&apos;t finished classifying it yet.
      </p>

      {/* Summary tiles */}
      <div className="mt-5 grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="debug-summary">
        <SummaryTile label="Records shown" value={stats.total} testId="debug-stat-total" />
        <SummaryTile
          label="Fully classified"
          value={stats.fullyClassified}
          hint={`${Math.round((stats.fullyClassified / (stats.total || 1)) * 100)}%`}
          tone="good"
          testId="debug-stat-full"
        />
        <SummaryTile
          label="Missing critical fields"
          value={stats.criticalGaps}
          hint="Queue / Readiness / Score"
          tone={stats.criticalGaps > 0 ? "warn" : "good"}
          testId="debug-stat-critical"
        />
        <SummaryTile
          label="Any gap"
          value={stats.anyGaps}
          hint="≥1 governed field null"
          testId="debug-stat-any"
        />
      </div>

      {/* Lane filter */}
      <div className="mt-5 flex items-center gap-1.5 flex-wrap" data-testid="debug-lane-filter">
        {LANE_FILTERS.map((f) => {
          const n = f.key === "all" ? items.length : laneCounts[f.key] || 0;
          const active = lane === f.key;
          return (
            <button
              key={f.key}
              type="button"
              onClick={() => setLane(f.key)}
              data-testid={`debug-lane-${f.key}`}
              className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md text-[11.5px] font-medium border transition-colors"
              style={{
                background: active ? "var(--bh-brass)" : "var(--bh-surface)",
                color: active ? "var(--bh-surface)" : "var(--bh-ink-2)",
                borderColor: active ? "var(--bh-brass)" : "var(--bh-hair-strong)",
              }}
            >
              {f.label} <span className="tabular-nums opacity-70">{n}</span>
            </button>
          );
        })}
      </div>

      {/* Table */}
      {loading ? (
        <div className="mt-6 text-[13px] text-[var(--bh-ink-3)]">Loading governed field snapshot…</div>
      ) : filtered.length === 0 ? (
        <div className="mt-6 text-[13px] text-[var(--bh-ink-3)]">No records match this filter.</div>
      ) : (
        <div
          className="mt-5 overflow-x-auto rounded-md border bh-hairline"
          style={{ background: "var(--bh-surface)" }}
        >
          <table className="min-w-full text-[11px]" data-testid="debug-table">
            <thead>
              <tr style={{ background: "var(--bh-surface-2)" }}>
                <th className="sticky left-0 z-10 text-left px-3 py-2 border-b bh-hairline font-semibold text-[var(--bh-ink-2)] mono uppercase tracking-widest text-[10px]"
                    style={{ background: "var(--bh-surface-2)" }}>
                  Record
                </th>
                <th className="text-left px-2 py-2 border-b bh-hairline mono uppercase tracking-widest text-[10px] text-[var(--bh-ink-mute)]">
                  Lane
                </th>
                {GOVERNED_FIELDS.map((f) => (
                  <th
                    key={f.key}
                    className="text-left px-2 py-2 border-b bh-hairline mono uppercase tracking-widest text-[10px] whitespace-nowrap"
                    style={{ color: f.critical ? "var(--bh-brass)" : "var(--bh-ink-mute)" }}
                    title={f.critical ? "Critical for the 3-bucket dashboard" : ""}
                  >
                    {f.label}
                    {f.critical && <span className="ml-1">*</span>}
                  </th>
                ))}
                <th className="border-b bh-hairline" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((o) => {
                const filledCount = GOVERNED_FIELDS.filter((f) => isFilled(o[f.key])).length;
                const critMissing = CRITICAL_KEYS.some((k) => !isFilled(o[k]));
                return (
                  <tr
                    key={o.id}
                    data-testid={`debug-row-${o.id}`}
                    className="hover:bg-[var(--bh-surface-2)]/60 transition-colors"
                  >
                    <td
                      className="sticky left-0 px-3 py-2 border-b bh-hairline align-top"
                      style={{ background: "var(--bh-surface)" }}
                    >
                      <div className="flex items-center gap-1.5">
                        {critMissing ? (
                          <AlertCircle size={11} className="text-[#c94a3b] shrink-0" />
                        ) : (
                          <CheckCircle2 size={11} className="text-[var(--bh-olive)] shrink-0" />
                        )}
                        <div className="font-medium text-[12px] text-[var(--bh-ink)] truncate max-w-[180px]" title={o.name}>
                          {o.name || "Untitled"}
                        </div>
                      </div>
                      <div className="mt-0.5 text-[10px] text-[var(--bh-ink-mute)] tabular-nums">
                        {filledCount}/{GOVERNED_FIELDS.length} fields
                      </div>
                    </td>
                    <td className="px-2 py-2 border-b bh-hairline align-top">
                      <LaneBadge lane={o.lane} />
                    </td>
                    {GOVERNED_FIELDS.map((f) => (
                      <Cell key={f.key} value={o[f.key]} />
                    ))}
                    <td className="px-2 py-2 border-b bh-hairline align-top">
                      <Link
                        to={`/opportunities/${o.id}`}
                        data-testid={`debug-open-${o.id}`}
                        className="inline-flex items-center gap-1 text-[10.5px] text-[var(--bh-brass)] hover:text-[var(--bh-ink)] whitespace-nowrap"
                      >
                        Open <ExternalLink size={9} />
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-4 text-[11px] text-[var(--bh-ink-3)] flex items-center gap-2 flex-wrap">
        <span className="inline-flex items-center gap-1">
          <span className="text-[var(--bh-brass)]">*</span> Critical — controls the 3-bucket dashboard
        </span>
        <span>·</span>
        <span>Governance is owned by Airtable + Make. Bloodhound reads only.</span>
      </div>
    </div>
  );
};

const SummaryTile = ({ label, value, hint, tone, testId }) => {
  const color =
    tone === "good"
      ? "var(--bh-olive)"
      : tone === "warn"
        ? "#c94a3b"
        : "var(--bh-ink)";
  return (
    <div
      data-testid={testId}
      className="rounded-md border p-3.5"
      style={{ background: "var(--bh-surface)", borderColor: "var(--bh-hair)" }}
    >
      <div className="mono text-[9.5px] uppercase tracking-widest text-[var(--bh-ink-mute)]">
        {label}
      </div>
      <div
        className="mt-1 font-display text-[24px] font-bold tabular-nums"
        style={{ color }}
      >
        {value}
      </div>
      {hint && (
        <div className="text-[10.5px] text-[var(--bh-ink-3)] mt-0.5">{hint}</div>
      )}
    </div>
  );
};

export default DebugPanel;
