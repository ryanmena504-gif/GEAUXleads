import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  Phone,
  Globe,
  MapPin,
  Building2,
  ExternalLink,
  Users,
} from "lucide-react";
import { api } from "@/lib/api";
import DiscoveryNav from "@/components/DiscoveryNav";
import FreshContactBadge from "@/components/FreshContactBadge";

/**
 * DiscoveryPropertyManagers — triage view for the Property Manager
 * Discovery Queue table.
 *
 * Claude + Make own the Review Status field. Bloodhound is a read-only
 * viewer: I see "Worth a look" candidates and tap to call / visit their
 * website. Promotion to the Leads pipeline happens on the data side.
 *
 * The list defaults to "Worth a look" (Claude's curated candidates). A
 * tab strip lets me switch to other statuses for context, but the
 * primary UX is Worth-a-Look first.
 */

const STATUS_TABS = [
  { key: "worth_a_look", label: "Worth a look", match: "worth a look" },
  { key: "new", label: "New", match: "new" },
  { key: "promoted_to_leads", label: "Promoted", match: "promoted to leads" },
  { key: "all", label: "All", match: null },
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

const StatusChip = ({ value }) => {
  if (!value) return null;
  const nv = normalize(value);
  let fg = "var(--bh-ink-mute)";
  let bg = "var(--bh-surface-2)";
  let border = "var(--bh-hair)";
  if (nv === "worth a look") {
    fg = "var(--bh-brass)";
    bg = "var(--bh-brass-mute)";
    border = "var(--bh-hair-warm)";
  } else if (nv === "promoted to leads") {
    fg = "var(--bh-olive)";
    bg = "var(--bh-olive-mute)";
    border = "rgba(107,122,85,0.32)";
  } else if (nv.startsWith("not relevant")) {
    fg = "#8a5a45";
    bg = "rgba(138,90,69,0.10)";
    border = "rgba(138,90,69,0.28)";
  }
  return (
    <span
      className="inline-flex items-center rounded-full border px-2 py-[1px] text-[10px] font-medium tracking-tight whitespace-nowrap"
      style={{ color: fg, background: bg, borderColor: border }}
    >
      {value}
    </span>
  );
};

const Row = ({ item }) => {
  const phone = item.phone ? digitsOnly(item.phone) : null;
  const domain = domainFromUrl(item.website);
  return (
    <div
      data-testid={`pm-row-${item.id}`}
      data-fresh={item.is_freshly_actionable ? "true" : "false"}
      className="bh-surface rounded-md p-4 hover:shadow-sm transition-shadow"
      style={{
        border: item.is_freshly_actionable ? "1px solid var(--bh-brass)" : "1px solid var(--bh-hair)",
        background: item.is_freshly_actionable ? "var(--bh-brass-mute)" : "var(--bh-surface)",
      }}
    >
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <Building2 size={13} className="text-[var(--bh-brass)] shrink-0" />
            <div
              className="font-display text-[16px] font-semibold text-[var(--bh-ink)] leading-tight truncate"
              data-testid={`pm-row-name-${item.id}`}
            >
              {item.name || "Unnamed property manager"}
            </div>
            {item.is_freshly_actionable && <FreshContactBadge testId={`pm-fresh-${item.id}`} />}
          </div>
          {item.portfolio_size && (
            <div className="mt-1 text-[11.5px] text-[var(--bh-ink-3)] inline-flex items-center gap-1">
              <Users size={10} strokeWidth={1.75} /> {item.portfolio_size} units
            </div>
          )}
          {item.address && (
            <div className="mt-1 text-[11.5px] text-[var(--bh-ink-3)] inline-flex items-center gap-1 truncate">
              <MapPin size={10} strokeWidth={1.75} /> {item.address}
            </div>
          )}
        </div>
        <StatusChip value={item.review_status} />
      </div>

      {item.notes && (
        <div className="mt-3 text-[12.5px] text-[var(--bh-ink-2)] leading-snug bh-surface-2 rounded-sm p-2.5">
          {item.notes}
        </div>
      )}

      <div className="mt-3 flex items-center gap-2 flex-wrap">
        {phone && (
          <a
            href={`tel:${phone}`}
            data-testid={`pm-call-${item.id}`}
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md text-[11.5px] font-medium border transition-colors"
            style={{
              background: "var(--bh-brass)",
              color: "var(--bh-surface)",
              borderColor: "var(--bh-brass)",
            }}
          >
            <Phone size={11} strokeWidth={2} /> Call {item.phone}
          </a>
        )}
        {domain && (
          <a
            href={item.website?.startsWith("http") ? item.website : `https://${item.website}`}
            target="_blank"
            rel="noopener noreferrer"
            data-testid={`pm-web-${item.id}`}
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md text-[11.5px] font-medium border transition-colors"
            style={{
              background: "var(--bh-surface)",
              color: "var(--bh-ink-2)",
              borderColor: "var(--bh-hair-strong)",
            }}
          >
            <Globe size={11} strokeWidth={2} /> {domain} <ExternalLink size={9} />
          </a>
        )}
        {!phone && !domain && (
          <span className="text-[11px] text-[var(--bh-ink-mute)] italic">
            No contact info yet — waiting on enrichment.
          </span>
        )}
      </div>
    </div>
  );
};

const DiscoveryPropertyManagers = () => {
  const [status, setStatus] = useState("worth_a_look");
  const [state, setState] = useState({ loading: true, items: [], counts: {} });

  useEffect(() => {
    let mounted = true;
    setState((s) => ({ ...s, loading: true }));
    api.discoveryPropertyManagers(status)
      .then((r) => mounted && setState({
        loading: false,
        items: r?.items || [],
        counts: r?.status_counts || {},
      }))
      .catch(() => mounted && setState({ loading: false, items: [], counts: {} }));
    return () => { mounted = false; };
  }, [status]);

  const totalKnown = useMemo(
    () => Object.values(state.counts).reduce((a, b) => a + (b || 0), 0),
    [state.counts],
  );

  const tabCount = (tab) => {
    if (tab.key === "all") return totalKnown;
    const target = tab.match;
    let total = 0;
    for (const [k, v] of Object.entries(state.counts)) {
      if (normalize(k) === target) total += v;
    }
    return total;
  };

  return (
    <div className="px-4 lg:px-8 py-6" data-testid="discovery-pm-page">
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-[12px] text-[var(--bh-ink-mute)] hover:text-[var(--bh-ink)] mb-4"
      >
        <ArrowLeft size={13} /> Home
      </Link>

      <DiscoveryNav />

      <div className="mono text-[10px] uppercase tracking-widest text-[var(--bh-brass)]">
        Discovery · Property managers
      </div>
      <h1
        className="mt-1 font-display text-[28px] font-bold text-[var(--bh-ink)] tracking-tight"
        data-testid="discovery-pm-headline"
      >
        Worth-a-look property managers
      </h1>
      <p className="mt-1 text-[13px] text-[var(--bh-ink-3)] max-w-3xl">
        Claude&apos;s curated shortlist from the Property Manager Discovery Queue.
        Tap to call or visit their website — every action opens native on your
        iPhone. Promoting a candidate into the Leads pipeline happens on the
        Airtable side.
      </p>

      {/* Status tabs */}
      <div className="mt-5 flex items-center gap-1.5 flex-wrap" data-testid="discovery-pm-tabs">
        {STATUS_TABS.map((tab) => {
          const n = tabCount(tab);
          const active = status === tab.key;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => setStatus(tab.key)}
              data-testid={`discovery-pm-tab-${tab.key}`}
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

      {/* List */}
      {state.loading ? (
        <div className="mt-6 text-[13px] text-[var(--bh-ink-3)]">Loading discovery queue…</div>
      ) : state.items.length === 0 ? (
        <div
          className="mt-6 bh-surface rounded-md p-6 text-[13px] text-[var(--bh-ink-3)] text-center"
          data-testid="discovery-pm-empty"
        >
          {status === "worth_a_look"
            ? "No candidates currently marked \"Worth a look\". Claude will surface more as Make classifies the queue."
            : "No records match this filter."}
        </div>
      ) : (
        <div className="mt-5 space-y-3">
          {state.items.map((item) => (
            <Row key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
};

export default DiscoveryPropertyManagers;
