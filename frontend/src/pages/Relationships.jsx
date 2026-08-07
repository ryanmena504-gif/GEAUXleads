import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import TopHeader from "@/components/TopHeader";
import LaneBadge from "@/components/LaneBadge";
import DraftNoteDrawer from "@/components/DraftNoteDrawer";
import OpenInMessages from "@/components/OpenInMessages";
import ContactBadge from "@/components/ContactBadge";
import { PriorityBand } from "@/components/PriorityBadge";
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
  PenLine,
} from "lucide-react";

const PartnerRow = ({ p, onDraft }) => {
  const partnerType = p.project_type || "Partner";
  const evidence = p.evidence_summary || p.signal_type;
  const why = p.recommendation_reason;
  const next = p.recommended_action || p.next_best_action;
  const url = p.source_url;
  return (
    <div
      data-testid={`partner-row-${p.id}`}
      className="bh-surface rounded-md p-4 hover:bg-white/[0.03] transition-colors duration-150"
    >
      <div className="flex items-start gap-4">
        <div className="hidden sm:flex flex-col items-start pt-1 w-[110px] shrink-0 gap-2">
          <PriorityBand band={p.priority_band} score={p.priority_score} />
          <ContactBadge opportunity={p} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Link
              to={`/opportunities/${p.id}`}
              data-testid={`partner-open-${p.id}`}
              className="font-display font-semibold text-neutral-100 hover:text-amber-300 truncate"
            >
              {p.name || "Unnamed"}
            </Link>
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
                What they do
              </span>
              {evidence}
            </div>
          )}
          {why && (
            <div className="mt-2 text-[13px] text-neutral-400 line-clamp-2">
              <span className="mono text-[10px] uppercase tracking-widest text-neutral-500 mr-2">
                Why they fit
              </span>
              {why}
            </div>
          )}
          {next && (
            <div className="mt-2 text-[13px] text-amber-200/90 line-clamp-2">
              <span className="mono text-[10px] uppercase tracking-widest text-neutral-500 mr-2">
                What to do next
              </span>
              {next}
            </div>
          )}
          <div className="mt-3 flex items-center gap-2 flex-wrap sm:hidden">
            <ContactBadge opportunity={p} />
          </div>
          <div className="mt-3 flex items-center gap-2 flex-wrap">
            {url && (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                data-testid={`partner-source-${p.id}`}
                className="mono text-[10px] uppercase tracking-widest text-sky-300 hover:text-sky-200 inline-flex items-center gap-1"
              >
                <ExternalLink size={11} /> Found on
              </a>
            )}
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onDraft(p);
              }}
              data-testid={`partner-draft-${p.id}`}
              className="mono text-[10px] uppercase tracking-widest inline-flex items-center gap-1 px-2 py-0.5 rounded border"
              style={{
                background: "var(--bh-brass-mute)",
                borderColor: "var(--bh-hair-warm)",
                color: "var(--bh-brass)",
              }}
            >
              <PenLine size={10} /> Draft a note
            </button>
            <div
              onClick={(e) => e.stopPropagation()}
              data-testid={`partner-handoff-${p.id}`}
              className="inline-flex"
            >
              <OpenInMessages opportunity={p} variant="pill" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const PartnerIntelligence = () => {
  const [items, setItems] = useState(null);
  const [tab, setTab] = useState("all");
  const [draftOpp, setDraftOpp] = useState(null);

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
        pageTitle="People to Know"
        subtitle={items === null ? "Loading" : `${items.length} builders, designers, and remodelers on file`}
      />
      <div className="px-4 lg:px-8 py-6 space-y-5">
        <section
          data-testid="partner-hero"
          className="bh-surface rounded p-5 sm:p-6 border-t border-t-emerald-500/60"
        >
          <div className="flex items-center gap-2">
            <Handshake size={13} style={{ color: "var(--bh-olive)" }} strokeWidth={1.75} />
            <span className="bh-eyebrow" style={{ color: "var(--bh-olive)" }}>
              People to know
            </span>
            <span className="bh-note ml-2 inline-flex items-center gap-1 py-0.5">
              <Shield size={10} strokeWidth={1.75} /> Nothing sends until you press Send on your phone
            </span>
          </div>
          <h2 className="mt-3 font-display text-[26px] sm:text-[32px] text-[var(--bh-ink)] tracking-tight max-w-2xl">
            Builders, designers, and remodelers who may send repeat work.
          </h2>
          <p className="mt-2 text-[14px] text-[var(--bh-ink-3)] max-w-2xl leading-relaxed">
            Everyone here has been flagged as a good repeat-work relationship.
            Tap Contact them to open a draft on your phone — you press Send
            when you&rsquo;re ready.
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
                "mono text-[10.5px] px-2.5 py-1 rounded-full border transition-colors duration-150 tracking-tight " +
                (tab === t.key
                  ? "bg-[var(--bh-olive-mute)] border-[rgba(107,122,85,0.32)] text-[var(--bh-olive)]"
                  : "bh-hairline text-[var(--bh-ink-mute)] hover:text-[var(--bh-ink)] hover:bg-[var(--bh-surface-2)]/70")
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
            Loading…
          </div>
        ) : visible.length === 0 ? (
          <div
            data-testid="partner-empty"
            className="bh-surface rounded p-10 border-t border-t-emerald-500/60 space-y-3"
          >
            <div className="flex items-center gap-2 text-neutral-300">
              <Users size={14} className="text-emerald-400" />
              <span className="font-display text-lg font-semibold">
                No people to know yet.
              </span>
            </div>
            <p className="text-sm text-neutral-500 max-w-lg leading-relaxed">
              Builders, designers, architects, and referral partners will show
              up here as soon as we find them.
            </p>
            <div className="inline-flex items-center gap-2 mono text-[10px] uppercase tracking-widest text-neutral-500 border bh-hairline rounded px-2 py-1">
              <AlertTriangle size={10} /> Nothing sends until you press Send on your phone
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            {visible.map((p) => (
              <PartnerRow key={p.id} p={p} onDraft={setDraftOpp} />
            ))}
          </div>
        )}

        <DraftNoteDrawer
          open={!!draftOpp}
          onOpenChange={(o) => !o && setDraftOpp(null)}
          opportunity={draftOpp}
        />

        <section className="text-xs text-neutral-500 flex items-center gap-2 justify-end pt-2">
          <ArrowRight size={11} />
          <span>Nothing sends automatically · you always press Send on your phone</span>
        </section>
      </div>
    </>
  );
};

export default PartnerIntelligence;
