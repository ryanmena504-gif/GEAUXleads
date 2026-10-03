import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { api } from "@/lib/api";

/**
 * Bench — the people Ryan builds repeat work with, on Home.
 *
 * Permits are one-off projects; the bench is landlords, property managers,
 * agents, investors and trade partners who send work again and again. Each
 * group shows a count and the first two names with the reason they're worth
 * a call, and links to its full list.
 *
 * Read-only: no messaging controls here. Each group's own page applies its
 * Outreach Gate before any draft can open.
 */

const firstLine = (s, max = 110) => {
  if (!s || typeof s !== "string") return null;
  const para = s.split("\n")[0];
  const stop = para.indexOf(". ");
  const line = (stop > 0 ? para.slice(0, stop + 1) : para).trim();
  return line.length > max ? `${line.slice(0, max - 1)}…` : line;
};

const portfolio = (n) => {
  const v = Number(n);
  return Number.isFinite(v) && v > 0 ? `${v} ${v === 1 ? "property" : "properties"}` : null;
};

const GROUPS = [
  {
    key: "landlords",
    label: "Small landlords",
    to: "/discovery/landlords",
    load: () => api.discoveryLandlords({ status: "not_contacted" }),
    pick: (r) => ({
      id: r.id,
      name: r.owner_name,
      why: [portfolio(r.portfolio_size), r.neighborhood, r.turnover_cadence && `turns over ${r.turnover_cadence.toLowerCase()}`]
        .filter(Boolean)
        .join(" · "),
    }),
  },
  {
    key: "property-managers",
    label: "Property managers",
    to: "/discovery/property-managers",
    load: () => api.discoveryPropertyManagers("worth_a_look"),
    pick: (r) => ({
      id: r.id,
      name: r.name,
      why: firstLine(r.notes) || [portfolio(r.portfolio_size), r.neighborhood].filter(Boolean).join(" · "),
    }),
  },
  {
    key: "agents",
    label: "Real estate agents",
    to: "/discovery/real-estate-agents",
    load: () => api.discoveryRealEstateAgents("all"),
    pick: (r) => ({
      id: r.id,
      name: r.name,
      why: firstLine(r.why_target) || r.brokerage,
    }),
  },
  {
    key: "investors",
    label: "Investors",
    to: "/discovery/investors",
    load: () => api.discoveryInvestors("all"),
    pick: (r) => ({
      id: r.id,
      name: r.name,
      why: firstLine(r.recommended_next_move) || firstLine(r.why_target) || portfolio(r.portfolio_size),
    }),
  },
  {
    key: "partners",
    label: "Trade partners",
    to: "/relationships",
    load: () =>
      api
        .listOpportunities({ lane: "partner" })
        .then((rows) => ({ items: rows.filter((o) => !["Won", "Lost", "Disqualified"].includes(o.status)) })),
    pick: (r) => ({
      id: r.id,
      name: r.name,
      why: firstLine(r.priority_explanation) || firstLine(r.current_recommendation) || r.project_type,
    }),
  },
];

const BenchGroup = ({ group, data }) => {
  const items = (data?.items || []).map(group.pick).filter((p) => p.name);
  return (
    <Link
      to={group.to}
      data-testid={`bench-${group.key}`}
      className="group block bh-surface rounded-md p-3 sm:p-4 min-w-0 hover:bg-[var(--bh-surface-2)] transition-colors duration-150"
    >
      <div className="flex items-baseline justify-between gap-3">
        <div className="text-[13px] font-semibold text-[var(--bh-ink)]">{group.label}</div>
        <div className="font-display text-[22px] leading-none tabular-nums text-[var(--bh-ink)]">
          {data ? items.length : "–"}
        </div>
      </div>
      <ul className="mt-3 space-y-2.5">
        {items.slice(0, 2).map((p) => (
          <li key={p.id} className="min-w-0">
            <div className="text-[13px] text-[var(--bh-ink-2)] truncate">{p.name}</div>
            {p.why && <div className="text-[11.5px] text-[var(--bh-ink-mute)] line-clamp-1">{p.why}</div>}
          </li>
        ))}
        {data && items.length === 0 && (
          <li className="text-[12px] text-[var(--bh-ink-mute)]">Nobody here yet.</li>
        )}
      </ul>
      <div className="mt-3 text-[11.5px] text-[var(--bh-ink-3)] group-hover:text-[var(--bh-ink)] inline-flex items-center gap-1">
        See all <ChevronRight size={12} />
      </div>
    </Link>
  );
};

const Bench = () => {
  const [data, setData] = useState({});

  useEffect(() => {
    let alive = true;
    GROUPS.forEach((g) => {
      g.load()
        .then((res) => alive && setData((prev) => ({ ...prev, [g.key]: res })))
        .catch(() => alive && setData((prev) => ({ ...prev, [g.key]: { items: [] } })));
    });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="grid gap-2 grid-cols-2 lg:grid-cols-3" data-testid="bench">
      {GROUPS.map((g) => (
        <BenchGroup key={g.key} group={g} data={data[g.key]} />
      ))}
    </div>
  );
};

export default Bench;
