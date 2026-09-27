import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  TrendingUp,
  Mail,
  Phone,
  Lock,
  Globe,
  ExternalLink,
  Users,
} from "lucide-react";
import { api } from "@/lib/api";
import DiscoveryNav from "@/components/DiscoveryNav";
import FreshContactBadge from "@/components/FreshContactBadge";
import DaysOnTable from "@/components/DaysOnTable";
import DiscoverySortToggle, { sortByDays } from "@/components/DiscoverySortToggle";

/**
 * DiscoveryInvestors — real estate investors / LLC entities tracking
 * multi-property portfolios. Mirrors the Real Estate Agent feed's
 * Outreach-Gate discipline: while Airtable says the gate is locked, no
 * mailto/tel buttons render. GEAUXleads is strictly a read-only viewer.
 *
 * Investor Intelligence table is currently empty pending Claude's data
 * seed. This page renders a "no investors yet" empty state that flips
 * to real rows the moment records land — no redeploy needed.
 */

const STATUS_TABS = [
  { key: "all", label: "All" },
  { key: "ready", label: "Ready to pitch" },
  { key: "locked", label: "Locked" },
];

const normalize = (s) => (s || "").toString().trim().toLowerCase();

const digitsOnly = (v) => (v || "").toString().replace(/[^\d+]/g, "");

const domainFromUrl = (u) => {
  if (!u) return null;
  try {
    const url = new URL(u.startsWith("http") ? u : `https://${u}`);
    return url.hostname.replace(/^www\./, "");
  } catch {
    return u.replace(/^https?:\/\/(www\.)?/, "").split("/")[0];
  }
};

const GateChip = ({ ready, gate }) => {
  const label = gate || (ready ? "Ready" : "Locked");
  const fg = ready ? "var(--bh-olive)" : "#8a5a45";
  const bg = ready ? "var(--bh-olive-mute)" : "rgba(138,90,69,0.10)";
  const border = ready ? "rgba(107,122,85,0.32)" : "rgba(138,90,69,0.28)";
  return (
    <span
      data-testid={`investor-gate-${ready ? "ready" : "locked"}`}
      className="inline-flex items-center gap-1 rounded-full border px-2 py-[1px] text-[10px] font-medium tracking-tight whitespace-nowrap"
      style={{ color: fg, background: bg, borderColor: border }}
    >
      {!ready && <Lock size={9} strokeWidth={2} />}
      {label}
    </span>
  );
};

const Row = ({ investor }) => {
  const phone = investor.outreach_ready && investor.phone ? digitsOnly(investor.phone) : null;
  const domain = domainFromUrl(investor.website);
  return (
    <div
      data-testid={`investor-row-${investor.id}`}
      data-fresh={investor.is_freshly_actionable ? "true" : "false"}
      className="bh-surface rounded-md p-4"
      style={{
        border: investor.is_freshly_actionable ? "1px solid var(--bh-brass)" : "1px solid var(--bh-hair)",
        background: investor.is_freshly_actionable ? "var(--bh-brass-mute)" : "var(--bh-surface)",
      }}
    >
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <TrendingUp size={13} className="text-[var(--bh-brass)] shrink-0" />
            <div
              className="font-display text-[16px] font-semibold text-[var(--bh-ink)] leading-tight truncate"
              data-testid={`investor-row-name-${investor.id}`}
            >
              {investor.name || "Unnamed entity"}
            </div>
            {investor.is_freshly_actionable && <FreshContactBadge testId={`investor-fresh-${investor.id}`} />}
            <DaysOnTable days={investor.days_on_table} testId={`investor-days-${investor.id}`} />
          </div>          <div className="mt-0.5 text-[12px] text-[var(--bh-ink-3)] flex items-center gap-2 flex-wrap">
            {investor.entity_type && <span>{investor.entity_type}</span>}
            {investor.principal && (
              <span className="inline-flex items-center gap-1">
                <Users size={10} strokeWidth={1.75} /> {investor.principal}
              </span>
            )}
          </div>
          {(investor.portfolio_size || investor.portfolio_value) && (
            <div className="mt-1 text-[11.5px] text-[var(--bh-ink-mute)] tabular-nums flex items-center gap-2 flex-wrap">
              {investor.portfolio_size && <span>{investor.portfolio_size} units</span>}
              {investor.portfolio_value && <span>· {typeof investor.portfolio_value === "number" ? `$${Number(investor.portfolio_value).toLocaleString()}` : investor.portfolio_value}</span>}
            </div>
          )}
        </div>
        <GateChip ready={investor.outreach_ready} gate={investor.outreach_gate} />
      </div>

      {investor.why_target && (
        <div className="mt-3 text-[12.5px] text-[var(--bh-ink-2)] leading-snug bh-surface-2 rounded-sm p-2.5">
          <span className="mono text-[9.5px] uppercase tracking-widest text-[var(--bh-ink-mute)] mr-1.5">
            Why:
          </span>
          {investor.why_target}
        </div>
      )}

      {investor.outreach_ready ? (
        <div className="mt-3 flex items-center gap-2 flex-wrap">
          {investor.email && (
            <a
              href={`mailto:${encodeURIComponent(investor.email)}`}
              data-testid={`investor-mailto-${investor.id}`}
              className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md text-[11.5px] font-medium border"
              style={{
                background: "var(--bh-brass)",
                color: "var(--bh-surface)",
                borderColor: "var(--bh-brass)",
              }}
            >
              <Mail size={11} strokeWidth={2} /> Email {investor.email}
            </a>
          )}
          {phone && (
            <a
              href={`tel:${phone}`}
              data-testid={`investor-call-${investor.id}`}
              className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md text-[11.5px] font-medium border"
              style={{
                background: "var(--bh-surface)",
                color: "var(--bh-ink-2)",
                borderColor: "var(--bh-hair-strong)",
              }}
            >
              <Phone size={11} strokeWidth={2} /> Call {investor.phone}
            </a>
          )}
          {domain && (
            <a
              href={investor.website.startsWith("http") ? investor.website : `https://${investor.website}`}
              target="_blank"
              rel="noopener noreferrer"
              data-testid={`investor-web-${investor.id}`}
              className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md text-[11.5px] font-medium border"
              style={{
                background: "var(--bh-surface)",
                color: "var(--bh-ink-2)",
                borderColor: "var(--bh-hair-strong)",
              }}
            >
              <Globe size={11} strokeWidth={2} /> {domain} <ExternalLink size={9} />
            </a>
          )}
          {!investor.email && !phone && !domain && (
            <span className="text-[11px] text-[var(--bh-ink-mute)] italic">
              Outreach unlocked but no contact yet.
            </span>
          )}
        </div>
      ) : (
        <div
          className="mt-3 flex items-center gap-1.5 text-[11px] text-[var(--bh-ink-3)]"
          data-testid={`investor-locked-note-${investor.id}`}
        >
          <Lock size={10} strokeWidth={1.75} />
          {investor.contact_enrichment_status || "Waiting on outreach gate"}
        </div>
      )}
    </div>
  );
};

const DiscoveryInvestors = () => {
  const [status, setStatus] = useState("all");
  const [state, setState] = useState({ loading: true, items: [], counts: {} });
  const [sortDir, setSortDir] = useState("fresh");

  useEffect(() => {
    let mounted = true;
    setState((s) => ({ ...s, loading: true }));
    api.discoveryInvestors(status)
      .then((r) => mounted && setState({
        loading: false,
        items: r?.items || [],
        counts: r?.status_counts || {},
      }))
      .catch(() => mounted && setState({ loading: false, items: [], counts: {} }));
    return () => { mounted = false; };
  }, [status]);

  const tabCount = (key) => state.counts?.[key] ?? 0;
  const sortedItems = useMemo(() => sortByDays(state.items, sortDir), [state.items, sortDir]);

  return (
    <div className="px-4 lg:px-8 py-6" data-testid="discovery-investors-page">
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-[12px] text-[var(--bh-ink-mute)] hover:text-[var(--bh-ink)] mb-4"
      >
        <ArrowLeft size={13} /> Home
      </Link>

      <DiscoveryNav />

      <div className="mono text-[10px] uppercase tracking-widest text-[var(--bh-brass)]">
        Discovery · Investors
      </div>
      <h1
        className="mt-1 font-display text-[28px] font-bold text-[var(--bh-ink)] tracking-tight"
        data-testid="discovery-investors-headline"
      >
        Investor intelligence
      </h1>
      <p className="mt-1 text-[13px] text-[var(--bh-ink-3)] max-w-3xl">
        Real estate investors and LLC entities tracking multi-property
        portfolios. GEAUXleads reads Claude&apos;s classified list — the moment
        an Outreach Gate unlocks and contact info lands, Email + Call
        buttons appear here automatically.
      </p>

      {/* Status tabs + sort */}
      <div className="mt-5 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-1.5 flex-wrap" data-testid="discovery-investors-tabs">
          {STATUS_TABS.map((tab) => {
            const n = tabCount(tab.key);
            const active = status === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => setStatus(tab.key)}
                data-testid={`discovery-investors-tab-${tab.key}`}
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
        <DiscoverySortToggle value={sortDir} onChange={setSortDir} testId="discovery-investors-sort" />
      </div>

      {/* List */}
      {state.loading ? (
        <div className="mt-6 text-[13px] text-[var(--bh-ink-3)]">Loading investor queue…</div>
      ) : state.items.length === 0 ? (
        <div
          className="mt-6 bh-surface rounded-md p-6 text-[13px] text-[var(--bh-ink-3)] text-center"
          data-testid="discovery-investors-empty"
        >
          The Investor Intelligence table is empty — Claude&apos;s classifier will
          seed records here. This page will light up automatically as they land.
        </div>
      ) : (
        <div className="mt-5 space-y-3">
          {sortedItems.map((investor) => (
            <Row key={investor.id} investor={investor} />
          ))}
        </div>
      )}

      <div className="mt-5 text-[10.5px] text-[var(--bh-ink-mute)] leading-snug">
        <ExternalLink size={9} className="inline mr-1 -mt-0.5" />
        Outreach Gate is owned by Airtable + Make. GEAUXleads never sends
        without the gate cleared.
      </div>
    </div>
  );
};

export default DiscoveryInvestors;
