import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Home, MapPin, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";
import { moneyDisplay, fmtDate } from "@/lib/formatters";

/**
 * LandlordPortfolio — property roll-up shown on OpportunityDetail for
 * landlord records. Groups sibling properties owned by the same landlord
 * (matched by shared email > phone tail > decision_maker name) and
 * lists them in a single card.
 *
 * Behaviour:
 *   • Fetches /api/opportunities/:id/portfolio on mount.
 *   • Renders nothing if the roll-up has <2 records (a single-property
 *     landlord shouldn't see an empty portfolio section).
 *   • Non-landlord records get an empty portfolio from the backend, so
 *     the caller can render this component unconditionally on any lane
 *     and it stays hidden.
 *   • Zero writes. Every row is a plain <Link> to /opportunities/:id.
 */

const QUEUE_STYLES = {
  "Ready to Contact": { fg: "var(--bh-brass)", bg: "var(--bh-brass-mute)", border: "var(--bh-hair-warm)" },
  Contacted: { fg: "var(--bh-olive)", bg: "var(--bh-olive-mute)", border: "rgba(107,122,85,0.32)" },
  "All Projects": { fg: "var(--bh-ink-mute)", bg: "var(--bh-surface-2)", border: "var(--bh-hair)" },
};

const MATCH_LABEL = {
  email: "shared email address",
  phone: "shared phone number",
  name: "shared contact name",
};

const QueueChip = ({ value }) => {
  if (!value) return null;
  const s = QUEUE_STYLES[value] || QUEUE_STYLES["All Projects"];
  return (
    <span
      className="inline-flex items-center rounded-full border px-2 py-[1px] text-[10px] font-medium tracking-tight"
      style={{ color: s.fg, background: s.bg, borderColor: s.border }}
    >
      {value}
    </span>
  );
};

const Row = ({ property }) => {
  const money = moneyDisplay(property);
  const lastTouch = property.last_turnover_check || property.date_contacted;
  return (
    <Link
      to={`/opportunities/${property.id}`}
      data-testid={`portfolio-row-${property.id}`}
      className="group flex items-start gap-3 px-3 py-2.5 -mx-3 rounded-md hover:bg-[var(--bh-surface-2)] transition-colors"
      style={{
        background: property.is_current ? "var(--bh-brass-mute)" : "transparent",
        border: property.is_current ? "1px solid var(--bh-hair-warm)" : "1px solid transparent",
      }}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="font-medium text-[13.5px] text-[var(--bh-ink)] group-hover:text-white truncate">
            {property.name || property.project_address || "Untitled property"}
          </div>
          {property.is_current && (
            <span
              data-testid="portfolio-row-current"
              className="mono text-[9px] uppercase tracking-widest px-1.5 py-[1px] rounded-sm"
              style={{ background: "var(--bh-brass)", color: "var(--bh-surface)" }}
            >
              Viewing
            </span>
          )}
          <QueueChip value={property.current_queue} />
        </div>
        {property.project_address && (
          <div className="mt-1 text-[11.5px] text-[var(--bh-ink-3)] inline-flex items-center gap-1 truncate">
            <MapPin size={10} strokeWidth={1.75} /> {property.project_address}
          </div>
        )}
        <div className="mt-1 text-[11px] text-[var(--bh-ink-mute)] tabular-nums flex items-center gap-2 flex-wrap">
          {typeof property.governed_priority_score === "number" && (
            <span>Score {property.governed_priority_score}</span>
          )}
          {money && <span>· {money}</span>}
          {property.turnover_cadence && (
            <span>· {property.turnover_cadence} cadence</span>
          )}
          {lastTouch && (
            <span>· Last touch {fmtDate(lastTouch)}</span>
          )}
        </div>
      </div>
      <ChevronRight
        size={13}
        className="mt-1 text-[var(--bh-ink-3)] group-hover:text-[var(--bh-brass)] shrink-0"
      />
    </Link>
  );
};

export const LandlordPortfolio = ({ opportunityId }) => {
  const [state, setState] = useState({ loading: true, portfolio: [], matchKey: null });

  useEffect(() => {
    let mounted = true;
    api.landlordPortfolio(opportunityId)
      .then((r) => mounted && setState({
        loading: false,
        portfolio: r?.portfolio || [],
        matchKey: r?.match_key || null,
      }))
      .catch(() => mounted && setState({ loading: false, portfolio: [], matchKey: null }));
    return () => { mounted = false; };
  }, [opportunityId]);

  // Only surface the roll-up when this landlord actually owns 2+ properties.
  // Single-property landlords, non-landlord records, and load failures all
  // render nothing.
  if (state.loading || state.portfolio.length < 2) return null;

  const otherCount = state.portfolio.length - 1;
  return (
    <section
      data-testid="landlord-portfolio"
      className="bh-surface rounded-md p-5 space-y-3"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <div
            className="mono text-[10px] uppercase tracking-widest inline-flex items-center gap-1.5"
            style={{ color: "#3f6b6b" }}
          >
            <Home size={11} strokeWidth={1.75} />
            Portfolio · {state.portfolio.length} properties
          </div>
          <div
            className="mt-1 font-display text-[16px] font-semibold text-[var(--bh-ink)] leading-tight"
            data-testid="portfolio-headline"
          >
            {otherCount} other {otherCount === 1 ? "property" : "properties"} owned by this landlord
          </div>
          {state.matchKey && (
            <div className="mt-1 text-[11.5px] text-[var(--bh-ink-3)]">
              Matched by {MATCH_LABEL[state.matchKey] || state.matchKey}
            </div>
          )}
        </div>
      </div>

      <div className="space-y-1 pt-1">
        {state.portfolio.map((p) => (
          <Row key={p.id} property={p} />
        ))}
      </div>
    </section>
  );
};

export default LandlordPortfolio;
