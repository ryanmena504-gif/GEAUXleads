import React, { useEffect, useState } from "react";
import { Trophy, TrendingUp, ClipboardList, Landmark } from "lucide-react";
import { api } from "@/lib/api";
import { fmtMoney } from "@/lib/formatters";

/**
 * WonThisMonth — a small hero strip showing the state of the business:
 *   • Won this month           (count + $ closed)
 *   • Active pipeline          (count + $ still in play)
 *   • Estimates out            (count + $ awaiting answer)
 *   • Won all-time             (count + $ closed since day one)
 *
 * Values come from /api/kpis/monthly which sums the opportunity list on the
 * fly — no separate tracking table needed. Silently hides if the endpoint
 * fails so the dashboard never breaks on the top row.
 */
const KPI_STYLES = {
  won:    { fg: "var(--bh-olive)", bg: "var(--bh-olive-mute)", border: "rgba(107,122,85,0.32)", icon: Trophy },
  active: { fg: "var(--bh-brass)", bg: "var(--bh-brass-mute)", border: "var(--bh-hair-warm)",   icon: TrendingUp },
  est:    { fg: "#4b6b6f",         bg: "rgba(75,107,111,0.08)", border: "rgba(75,107,111,0.28)", icon: ClipboardList },
  alltime:{ fg: "var(--bh-ink-2)", bg: "var(--bh-surface-2)",   border: "var(--bh-hair)",        icon: Landmark },
};

const KpiTile = ({ kind, label, count, value, hint, testId }) => {
  const s = KPI_STYLES[kind] || KPI_STYLES.active;
  const Icon = s.icon;
  return (
    <div
      data-testid={testId}
      className="rounded-md p-4 flex items-start gap-3 border"
      style={{ background: s.bg, borderColor: s.border }}
    >
      <div
        className="w-9 h-9 shrink-0 rounded-full flex items-center justify-center"
        style={{ background: "var(--bh-surface)", border: `1px solid ${s.border}` }}
      >
        <Icon size={15} strokeWidth={1.75} style={{ color: s.fg }} />
      </div>
      <div className="min-w-0">
        <div
          className="mono text-[10px] uppercase tracking-widest"
          style={{ color: s.fg }}
        >
          {label}
        </div>
        <div className="mt-1 flex items-baseline gap-2 flex-wrap">
          <span
            className="font-display text-2xl font-bold tabular-nums leading-none"
            style={{ color: s.fg }}
          >
            {fmtMoney(value ?? 0)}
          </span>
          <span className="text-[11px] text-[var(--bh-ink-mute)] tabular-nums">
            · {count ?? 0} {count === 1 ? "project" : "projects"}
          </span>
        </div>
        {hint && (
          <div className="mt-1.5 text-[11.5px] text-[var(--bh-ink-3)] leading-tight">
            {hint}
          </div>
        )}
      </div>
    </div>
  );
};

export const WonThisMonth = () => {
  const [kpis, setKpis] = useState(null);

  useEffect(() => {
    let mounted = true;
    api
      .monthlyKpis()
      .then((r) => mounted && setKpis(r))
      .catch(() => mounted && setKpis(null));
    return () => {
      mounted = false;
    };
  }, []);

  if (!kpis) return null;

  // Month label — "August 2026" style, using the returned month_start ISO.
  let monthLabel = "this month";
  try {
    const d = new Date(kpis.month_start);
    monthLabel = d.toLocaleString(undefined, { month: "long", year: "numeric" });
  } catch (err) {
    // Bad date string from the API — surface it so we notice, then fall
    // back to the generic label.
    console.warn("WonThisMonth: bad month_start", kpis.month_start, err);
  }

  return (
    <section
      data-testid="section-won-this-month"
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3"
    >
      <KpiTile
        kind="won"
        label={`Won · ${monthLabel}`}
        count={kpis.won_this_month?.count}
        value={kpis.won_this_month?.value}
        hint={
          (kpis.won_this_month?.count || 0) === 0
            ? "Book your first Won of the month"
            : "Nice work — keep the streak going"
        }
        testId="kpi-won-month"
      />
      <KpiTile
        kind="active"
        label="Active pipeline"
        count={kpis.active_pipeline?.count}
        value={kpis.active_pipeline?.value}
        hint="Still in play across every lane"
        testId="kpi-active-pipeline"
      />
      <KpiTile
        kind="est"
        label="Estimates out"
        count={kpis.estimates_out?.count}
        value={kpis.estimates_out?.value}
        hint="Waiting on the customer to say yes"
        testId="kpi-estimates-out"
      />
      <KpiTile
        kind="alltime"
        label="Won all-time"
        count={kpis.won_all_time?.count}
        value={kpis.won_all_time?.value}
        hint="Every project you've closed"
        testId="kpi-won-alltime"
      />
    </section>
  );
};

export default WonThisMonth;
