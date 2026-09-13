import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Sun, Coffee, Flag, Clock, ChevronRight, ArrowRight, Home } from "lucide-react";
import { api } from "@/lib/api";
import { moneyDisplay } from "@/lib/formatters";

/**
 * MorningBrief — the same content that ships in the 7am email, rendered as
 * a calm panel at the top of Home. Reads /api/morning-brief/preview so the
 * email body and the in-app view can never drift.
 *
 * Show/hide rule:
 *   • On mount, fetch the brief.
 *   • If the operator has already dismissed it today (localStorage), skip.
 *   • If it's outside the "morning" window (5:00–11:59 local), still render
 *     if the total > 0 — Ryan can open the app at noon and still want the
 *     summary — but with a slightly muted eyebrow.
 *   • If the brief has zero items across all three sections, hide.
 *
 * Guardrails:
 *   • No writes. Every row is a plain <Link> to /opportunities/:id.
 *   • Dismiss is UI-only (localStorage). Nothing hits the backend.
 */

const DISMISS_KEY = () => `morning-brief-dismissed:${new Date().toISOString().slice(0, 10)}`;

const isMorningWindow = () => {
  const h = new Date().getHours();
  return h >= 5 && h < 12;
};

const Section = ({ eyebrow, icon: Icon, items, emptyText, renderNote }) => {
  if (!items || items.length === 0) return null;
  return (
    <div className="pt-3 border-t bh-hairline first:border-t-0 first:pt-0">
      <div className="flex items-center gap-2">
        <Icon size={13} className="text-[var(--bh-brass)]" strokeWidth={1.75} />
        <span className="bh-eyebrow" style={{ color: "var(--bh-brass)" }}>{eyebrow}</span>
      </div>
      <div className="mt-2 space-y-1.5">
        {items.map((r) => (
          <Link
            key={r.id}
            to={`/opportunities/${r.id}`}
            data-testid={`morning-brief-row-${r.id}`}
            className="group flex items-start gap-3 px-2.5 py-2 -mx-2.5 rounded-md hover:bg-[var(--bh-surface-2)] transition-colors"
          >
            <div className="min-w-0 flex-1">
              <div className="font-medium text-[13.5px] text-[var(--bh-ink)] group-hover:text-white truncate">
                {r.name}
              </div>
              <div className="mt-0.5 text-[11.5px] text-[var(--bh-ink-3)] truncate">
                {r.project_type ? `${r.project_type} · ` : ""}
                {(() => { const m = moneyDisplay(r); return m ? `${m} · ` : ""; })()}
                {typeof r.governed_priority_score === "number" ? `Score ${r.governed_priority_score}` : ""}
              </div>
              <div className="mt-1 text-[11.5px] text-amber-200/85 leading-snug">
                {renderNote(r)}
              </div>
            </div>
            <ChevronRight size={13} className="mt-1 text-[var(--bh-ink-3)] group-hover:text-[var(--bh-brass)]" />
          </Link>
        ))}
        {emptyText && items.length === 0 && (
          <div className="text-[12px] text-[var(--bh-ink-3)] italic">{emptyText}</div>
        )}
      </div>
    </div>
  );
};

const MorningBrief = () => {
  const [brief, setBrief] = useState(null);
  const [dismissed, setDismissed] = useState(
    typeof window !== "undefined" && localStorage.getItem(DISMISS_KEY()) === "1",
  );

  useEffect(() => {
    if (dismissed) return;
    let mounted = true;
    api.morningBrief()
      .then((r) => mounted && setBrief(r))
      .catch(() => mounted && setBrief(null));
    return () => { mounted = false; };
  }, [dismissed]);

  if (dismissed || !brief) return null;
  const total = brief.counts?.total || 0;
  if (total === 0) return null;

  const inWindow = isMorningWindow();
  return (
    <section
      data-testid="section-morning-brief"
      className="rounded-md border p-5 space-y-4"
      style={{
        background: "var(--bh-surface)",
        borderColor: "var(--bh-hair-warm)",
        boxShadow: "0 1px 0 rgba(138,106,43,0.04)",
      }}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <div
            className="mono text-[10px] uppercase tracking-widest"
            style={{ color: inWindow ? "var(--bh-brass)" : "var(--bh-ink-mute)" }}
          >
            <Sun size={11} className="inline-block -mt-0.5 mr-1.5" strokeWidth={1.75} />
            {inWindow ? "Morning brief" : "Today's brief"}
          </div>
          <div
            className="mt-1 font-display text-[19px] font-semibold text-[var(--bh-ink)] leading-tight"
            data-testid="morning-brief-headline"
          >
            {total} {total === 1 ? "thing" : "things"} want your attention this morning.
          </div>
          <div className="mt-1 text-[12.5px] text-[var(--bh-ink-3)]">
            Every row opens the record so you can review before texting or emailing — nothing sends until you press Send yourself.
          </div>
        </div>
        <button
          type="button"
          data-testid="morning-brief-dismiss"
          onClick={() => {
            localStorage.setItem(DISMISS_KEY(), "1");
            setDismissed(true);
          }}
          className="text-[11.5px] text-[var(--bh-ink-3)] hover:text-[var(--bh-ink)] px-2 py-1 rounded"
        >
          Dismiss
        </button>
      </div>

      <div className="space-y-3">
        <Section
          eyebrow={`New Ready (${brief.counts?.new_ready || 0})`}
          icon={Flag}
          items={brief.new_ready || []}
          renderNote={(r) => `Promoted ${r.hours_since_ready}h ago · ${r.current_recommendation || "Ready for first contact"}`}
        />
        <Section
          eyebrow={`Follow-ups due (${brief.counts?.follow_ups || 0})`}
          icon={ArrowRight}
          items={brief.follow_ups || []}
          renderNote={(r) => `${r.bucket_label} · ${r.days_since_touch} days since last ${r.last_channel}`}
        />
        <Section
          eyebrow={`Turnover check-ins (${brief.counts?.turnover_checkins || 0})`}
          icon={Home}
          items={brief.turnover_checkins || []}
          renderNote={(r) => {
            const cadence = r.cadence && r.cadence !== "Unknown" ? `${r.cadence} cadence` : "Cadence unknown";
            const since = r.days_since_touch == null ? "never nudged" : `${r.days_since_touch} days since last touch`;
            return `${cadence} · ${since}`;
          }}
        />
        <Section
          eyebrow={`Estimate deadlines (${brief.counts?.estimate_nudges || 0})`}
          icon={Clock}
          items={brief.estimate_nudges || []}
          renderNote={(r) => `Estimate sent ${r.days_since_reply} days ago`}
        />
      </div>

      <div className="pt-3 border-t bh-hairline flex items-center gap-2 text-[11.5px] text-[var(--bh-ink-3)]">
        <Coffee size={11} strokeWidth={1.75} className="text-[var(--bh-ink-mute)]" />
        Delivered to your inbox every morning at 7am. Adjust in Settings when we ship the toggle.
      </div>
    </section>
  );
};

export default MorningBrief;
