import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import TopHeader from "@/components/TopHeader";
import LaneBadge from "@/components/LaneBadge";
import { PriorityBand, PriorityScore } from "@/components/PriorityBadge";
import { api } from "@/lib/api";
import { useLiveUpdates } from "@/hooks/useLiveUpdates";
import {
  Handshake,
  ExternalLink,
  Lock,
  Users,
  MapPin,
  Shield,
  AlertTriangle,
  ArrowRight,
} from "lucide-react";

const PartnerRow = ({ p }) => {
  const partnerType = p.project_type || "Unclassified partner";
  const evidence = p.evidence_summary || p.signal_type;
  const why = p.recommendation_reason;
  const next = p.recommended_action || p.next_best_action;
  const url = p.source_url;
  const rel = p.status || p.ryans_decision;
  const score = p.priority_score;
  const confidence = p.evidence_confidence || p.contact_confidence;
  return (
    <div
      data-testid={`partner-row-${p.id}`}
      className="bh-surface rounded-md p-4 hover:bg-white/[0.03] transition-colors duration-150"
    >
      <div className="flex items-start gap-4">
        <div className="hidden sm:flex flex-col items-center pt-1 w-14 shrink-0">
          <PriorityScore score={score} band={p.priority_band} size="md" />
          <PriorityBand band={p.priority_band} className="mt-1.5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Link
              to={`/opportunities/${p.id}`}
              data-testid={`partner-open-${p.id}`}
              className="font-display font-semibold text-neutral-100 hover:text-amber-300 truncate"
            >
              {p.name || "Unnamed partner"}
            </Link>
            <span className="mono text-[10px] text-neutral-500">{p.opportunity_id}</span>
            <LaneBadge lane={p.lane || "partner"} />
          </div>
          <div className="mt-1 flex items-center gap-3 text-xs text-neutral-400 flex-wrap">
            <span className="mono text-[10px] uppercase tracking-widest text-neutral-500">
              {partnerType}
            </span>
            {p.company && <span>· {p.company}</span>}
            {p.project_address && (
              <span className="inline-flex items-center gap-1">
                <MapPin size={11} className="text-neutral-500" /> {p.project_address}
              </span>
            )}
          </div>
          {evidence && (
            <div className="mt-2 text-sm text-neutral-300 line-clamp-2">
              <span className="mono text-[10px] uppercase tracking-widest text-neutral-500 mr-2">
                Evidence
              </span>
              {evidence}
            </div>
          )}
          {why && (
            <div className="mt-2 text-[13px] text-neutral-400 line-clamp-2">
              <span className="mono text-[10px] uppercase tracking-widest text-neutral-500 mr-2">
                Why
              </span>
              {why}
            </div>
          )}
          {next && (
            <div className="mt-2 text-[13px] text-amber-200/90 line-clamp-2">
              <span className="mono text-[10px] uppercase tracking-widest text-neutral-500 mr-2">
                Next
              </span>
              {next}
            </div>
          )}
          <div className="mt-3 flex items-center gap-2 flex-wrap">
            {rel && (
              <span className="mono text-[10px] uppercase tracking-widest text-neutral-400 border bh-hairline rounded px-2 py-0.5">
                Relationship · {rel}
              </span>
            )}
            {confidence && (
              <span className="mono text-[10px] uppercase tracking-widest text-neutral-400 border bh-hairline rounded px-2 py-0.5">
                Confidence · {confidence}
              </span>
            )}
            {url && (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                data-testid={`partner-source-${p.id}`}
                className="mono text-[10px] uppercase tracking-widest text-sky-300 hover:text-sky-200 inline-flex items-center gap-1"
              >
                <ExternalLink size={11} /> Source
              </a>
            )}
            <span className="mono text-[10px] uppercase tracking-widest text-neutral-500 border bh-hairline rounded px-2 py-0.5 inline-flex items-center gap-1">
              <Lock size={10} /> Campaign approval required
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

const PartnerIntelligence = () => {
  const [items, setItems] = useState(null);
  const [tab, setTab] = useState("all");

  const load = React.useCallback(() => {
    api.listOpportunities({ lane: "partner" }).then(setItems);
  }, []);
  useEffect(() => { load(); }, [load]);
  useLiveUpdates(React.useCallback(() => load(), [load]));

  const grouped = useMemo(() => {
    const g = { contractor: [], designer: [], architect: [], supplier: [], referral: [], other: [] };
    (items || []).forEach((p) => {
      const t = (p.project_type || "").toLowerCase();
      if (t.includes("contractor") || t.includes("remodel")) g.contractor.push(p);
      else if (t.includes("designer")) g.designer.push(p);
      else if (t.includes("architect")) g.architect.push(p);
      else if (t.includes("supplier") || t.includes("vendor")) g.supplier.push(p);
      else if (t.includes("referral") || t.includes("partner")) g.referral.push(p);
      else g.other.push(p);
    });
    return g;
  }, [items]);

  const visible = useMemo(() => {
    if (tab === "all") return items || [];
    return grouped[tab] || [];
  }, [tab, grouped, items]);

  const TABS = [
    { key: "all", label: "All" },
    { key: "contractor", label: "Contractors" },
    { key: "designer", label: "Designers" },
    { key: "architect", label: "Architects" },
    { key: "supplier", label: "Suppliers" },
    { key: "referral", label: "Referral partners" },
  ];

  return (
    <>
      <TopHeader
        pageTitle="Partner Intelligence"
        subtitle={items === null ? "Loading…" : `${items.length} qualified partners`}
      />
      <div className="px-4 lg:px-8 py-6 space-y-5">
        <section
          data-testid="partner-hero"
          className="bh-surface rounded p-5 sm:p-6 border-t border-t-emerald-500/60"
        >
          <div className="flex items-center gap-2">
            <Handshake size={13} className="text-emerald-400" />
            <span className="mono text-[10px] uppercase tracking-widest text-emerald-400">
              Partner Pipeline
            </span>
            <span className="mono text-[10px] uppercase tracking-widest text-neutral-500 border bh-hairline rounded px-2 py-0.5 inline-flex items-center gap-1 ml-2">
              <Shield size={10} /> Read-only intelligence · no outreach
            </span>
          </div>
          <h2 className="mt-2 font-display text-2xl sm:text-3xl font-bold text-neutral-100 tracking-tight max-w-2xl">
            Qualified contractors, designers, architects, and referral partners.
          </h2>
          <p className="mt-2 text-sm text-neutral-400 max-w-2xl leading-relaxed">
            Every row here is a qualified relationship candidate the Airtable
            model has flagged as a partner. Contact automation is disabled by
            design — send only after a campaign is approved.
          </p>
        </section>

        <section className="flex flex-wrap gap-1.5">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              data-testid={`partner-tab-${t.key}`}
              onClick={() => setTab(t.key)}
              className={
                "mono text-[10px] uppercase tracking-widest px-2.5 py-1 rounded border transition-colors duration-150 " +
                (tab === t.key
                  ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-300"
                  : "bh-hairline text-neutral-400 hover:text-neutral-200 hover:bg-white/[0.03]")
              }
            >
              {t.label}
              <span className="ml-1.5 text-neutral-500 normal-case tracking-normal">
                {t.key === "all"
                  ? (items?.length ?? 0)
                  : (grouped[t.key]?.length ?? 0)}
              </span>
            </button>
          ))}
        </section>

        {items === null ? (
          <div className="bh-surface rounded p-12 text-center text-neutral-500 text-sm">
            Loading partner intelligence…
          </div>
        ) : visible.length === 0 ? (
          <div
            data-testid="partner-empty"
            className="bh-surface rounded p-10 border-t border-t-emerald-500/60 space-y-3"
          >
            <div className="flex items-center gap-2 text-neutral-300">
              <Users size={14} className="text-emerald-400" />
              <span className="font-display text-lg font-semibold">
                No partner records yet.
              </span>
            </div>
            <p className="text-sm text-neutral-500 max-w-lg leading-relaxed">
              Your automation hasn&apos;t flagged any leads as partners in the
              Airtable base yet. Partners will surface here the moment the
              automation writes any of:
            </p>
            <ul className="mono text-[11px] uppercase tracking-widest text-neutral-500 space-y-1 pl-1">
              <li>· Partnership potential = checked</li>
              <li>· Opportunity type contains &quot;Contractor / Designer / Architect / Supplier / Referral&quot;</li>
              <li>· Source category or Source contains &quot;Partner / Referral / Network / Trade&quot;</li>
            </ul>
            <div className="inline-flex items-center gap-2 mono text-[10px] uppercase tracking-widest text-neutral-500 border bh-hairline rounded px-2 py-1">
              <AlertTriangle size={10} /> No outreach — campaign approval required
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            {visible.map((p) => (
              <PartnerRow key={p.id} p={p} />
            ))}
          </div>
        )}

        <section className="text-xs text-neutral-500 flex items-center gap-2 justify-end pt-2">
          <ArrowRight size={11} />
          <span>Airtable read-only projection · no writes performed on this page</span>
        </section>
      </div>
    </>
  );
};

export default PartnerIntelligence;
