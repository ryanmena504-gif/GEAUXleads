import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Printer } from "lucide-react";
import TopHeader from "@/components/TopHeader";
import { api } from "@/lib/api";
import { buildDoorHangerRoute } from "@/lib/doorHangers";
import { isMailDoorLead } from "@/lib/mailDoor";

/**
 * DoorHangerRoute — the weekly walking list for permit leads nobody can
 * call or email yet. Open permit leads with an address and no phone or
 * email, grouped by ZIP / neighborhood, streets in order. "Print route"
 * prints just the list (app chrome hidden) with a check box per door.
 *
 * Read-only: nothing here writes to Airtable or contacts anyone.
 */
const weekOf = () => {
  const d = new Date();
  const monday = new Date(d);
  monday.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return monday.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
};

const permitLine = (opp) =>
  [opp.project_type, opp.permit_number].filter(Boolean).join(" · ");

const DoorHangerRoute = () => {
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .listOpportunities()
      .then((rows) => setItems(rows))
      .catch(() => {
        setItems([]);
        setError("Couldn't load your leads — the GEAUXleads API didn't respond.");
      });
  }, []);

  const route = useMemo(() => (Array.isArray(items) ? buildDoorHangerRoute(items) : null), [items]);
  const total = route ? route.reduce((n, g) => n + g.stops.length, 0) : 0;

  return (
    <>
      <div className="no-print">
        <TopHeader pageTitle="Door-hanger route" subtitle="Mail, door hangers, and knocks — no calls or texts" />
      </div>
      <main className="door-route px-4 lg:px-8 py-6 pb-28 max-w-4xl space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-display text-[26px] tracking-tight text-[var(--bh-ink)]">
              Week of {weekOf()}
            </h1>
            <p className="text-[13px] text-[var(--bh-ink-mute)] mt-0.5">
              {route ? `${total} doors in ${route.length} areas.` : "Loading…"} A hanger or a postcard
              only needs the address. No calls or texts from this list.
            </p>
          </div>
          <button
            type="button"
            onClick={() => window.print()}
            disabled={!route || total === 0}
            data-testid="door-route-print"
            className="no-print inline-flex items-center gap-1.5 h-10 px-4 rounded-md text-[13px] font-semibold disabled:opacity-50"
            style={{ background: "var(--bh-brass)", color: "var(--bh-surface)" }}
          >
            <Printer size={14} /> Print route
          </button>
        </div>

        {error && (
          <div role="alert" className="no-print bh-surface rounded-md p-4 text-sm text-red-300">
            {error}
          </div>
        )}

        {route && total === 0 && !error && (
          <div className="bh-surface rounded-md p-6 text-center text-sm text-[var(--bh-ink-mute)]">
            No open permit leads without a phone or email right now.
          </div>
        )}

        {route &&
          route.map((group) => (
            <section key={group.zip} data-testid={`door-route-zip-${group.zip}`} className="door-route-group space-y-2">
              <h2 className="flex items-baseline justify-between border-b bh-hairline pb-1.5">
                <span className="font-display text-[19px] tracking-tight text-[var(--bh-ink)]">{group.label}</span>
                <span className="text-[12px] text-[var(--bh-ink-mute)]">{group.stops.length} doors</span>
              </h2>
              <ol className="space-y-1.5">
                {group.stops.map((opp) => (
                  <li key={opp.id} data-testid={`door-route-stop-${opp.id}`} className="door-route-stop flex items-start gap-3">
                    <span aria-hidden="true" className="door-route-box mt-1 inline-block h-3.5 w-3.5 shrink-0 rounded-sm border border-[var(--bh-ink-mute)]" />
                    <div className="min-w-0">
                      <Link to={`/opportunities/${opp.id}`} className="text-[14.5px] text-[var(--bh-ink)] hover:underline">
                        {opp.project_address}
                      </Link>
                      {permitLine(opp) && (
                        <div className="text-[12px] text-[var(--bh-ink-mute)]">{permitLine(opp)}</div>
                      )}
                      {isMailDoorLead(opp) && (
                        <div className="text-[11px] uppercase tracking-wide text-[var(--bh-brass)]">Mail / door knock</div>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          ))}
      </main>
      <style>{`
        @media print {
          .no-print { display: none !important; }
          aside[data-testid="sidebar"],
          nav[data-testid="bottom-nav"],
          .bottom-nav { display: none !important; }
          main[data-testid="app-main"] { padding: 0 !important; }
          html, body { background: #ffffff !important; }
          .door-route, .door-route * { color: #111 !important; background: transparent !important; }
          .door-route { max-width: none; padding: 0 !important; }
          .door-route-group { break-inside: avoid-page; }
          .door-route-stop { break-inside: avoid; }
          .door-route-box { border-color: #111 !important; }
          .door-route a { text-decoration: none; }
          @page { size: letter; margin: 0.5in; }
        }
      `}</style>
    </>
  );
};

export default DoorHangerRoute;
