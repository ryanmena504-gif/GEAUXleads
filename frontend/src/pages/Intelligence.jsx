import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import TopHeader from "@/components/TopHeader";
import LaneBadge from "@/components/LaneBadge";
import { PriorityBand, PriorityScore } from "@/components/PriorityBadge";
import { api } from "@/lib/api";
import { useLiveUpdates } from "@/hooks/useLiveUpdates";
import {
  Radar,
  ExternalLink,
  Lock,
  Sparkles,
  Shield,
  AlertTriangle,
  ArrowRight,
} from "lucide-react";

const SignalRow = ({ s }) => {
  const evidence = s.evidence_summary || s.signal_type;
  const why = s.recommendation_reason;
  const next = s.recommended_action || s.next_best_action;
  const url = s.source_url;
  const source = s.source_category || s.source;
  const fit = s.project_type || s.opportunity_fit;
  const confidence = s.evidence_confidence || s.contact_confidence;
  return (
    <div
      data-testid={`signal-row-${s.id}`}
      className="bh-surface rounded-md p-4 hover:bg-white/[0.03] transition-colors duration-150"
    >
      <div className="flex items-start gap-4">
        <div className="hidden sm:flex flex-col items-center pt-1 w-14 shrink-0">
          <PriorityScore score={s.priority_score} band={s.priority_band} size="md" />
          <PriorityBand band={s.priority_band} className="mt-1.5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Link
              to={`/opportunities/${s.id}`}
              data-testid={`signal-open-${s.id}`}
              className="font-display font-semibold text-neutral-100 hover:text-amber-300 truncate"
            >
              {s.name || "Unnamed signal"}
            </Link>
            <span className="mono text-[10px] text-neutral-500">{s.opportunity_id}</span>
            <LaneBadge lane={s.lane || "non_permit"} />
          </div>
          <div className="mt-1 flex items-center gap-2 text-xs text-neutral-400 flex-wrap">
            {source && (
              <span className="mono text-[10px] uppercase tracking-widest text-sky-300 border border-sky-500/30 rounded px-2 py-0.5">
                {source}
              </span>
            )}
            {fit && (
              <span className="mono text-[10px] uppercase tracking-widest text-neutral-400 border bh-hairline rounded px-2 py-0.5">
                Fit · {fit}
              </span>
            )}
          </div>
          {evidence && (
            <div className="mt-2 text-sm text-neutral-300 line-clamp-2">
              <span className="mono text-[10px] uppercase tracking-widest text-neutral-500 mr-2">
                Signal
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
                data-testid={`signal-evidence-${s.id}`}
                className="mono text-[10px] uppercase tracking-widest text-sky-300 hover:text-sky-200 inline-flex items-center gap-1"
              >
                <ExternalLink size={11} /> Evidence
              </a>
            )}
            <span className="mono text-[10px] uppercase tracking-widest text-neutral-500 border bh-hairline rounded px-2 py-0.5 inline-flex items-center gap-1">
              <Lock size={10} /> Public signal is not permission to contact
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

const NonPermitSignals = () => {
  const [items, setItems] = useState(null);
  const [platform, setPlatform] = useState("all");

  const load = React.useCallback(() => {
    api.listOpportunities({ lane: "non_permit" }).then(setItems);
  }, []);
  useEffect(() => { load(); }, [load]);
  useLiveUpdates(React.useCallback(() => load(), [load]));

  const platforms = useMemo(() => {
    const set = new Set();
    (items || []).forEach((s) => {
      if (s.source_category) set.add(s.source_category);
      else if (s.source) set.add(s.source);
    });
    return ["all", ...Array.from(set)];
  }, [items]);

  const visible = useMemo(() => {
    if (platform === "all") return items || [];
    return (items || []).filter(
      (s) => (s.source_category || s.source) === platform,
    );
  }, [platform, items]);

  return (
    <>
      <TopHeader
        pageTitle="Market Notes"
        subtitle={items === null ? "Loading" : `${items.length} non-permit signals worth reading`}
      />
      <div className="px-4 lg:px-8 py-6 space-y-5">
        <section
          data-testid="signals-hero"
          className="bh-surface rounded p-5 sm:p-6 border-t border-t-sky-500/60"
        >
          <div className="flex items-center gap-2">
            <Radar size={13} style={{ color: "#4b6b6f" }} strokeWidth={1.75} />
            <span className="bh-eyebrow" style={{ color: "#4b6b6f" }}>
              Market notes
            </span>
            <span className="bh-note ml-2 inline-flex items-center gap-1 py-0.5">
              <Shield size={10} strokeWidth={1.75} /> Read-only · approval required before outreach
            </span>
          </div>
          <h2 className="mt-3 font-display text-[26px] sm:text-[32px] text-[var(--bh-ink)] tracking-tight max-w-2xl">
            Project signals from outside the permit feed.
          </h2>
          <p className="mt-2 text-[14px] text-[var(--bh-ink-3)] max-w-2xl leading-relaxed">
            Website mentions, referral hints, and other non-permit evidence
            the automation has qualified as project-relevant. A public signal
            is not permission to contact — reach out only after a campaign is
            approved.
          </p>
        </section>

        {platforms.length > 1 && (
          <section className="flex flex-wrap gap-1.5">
            {platforms.map((p) => (
              <button
                key={p}
                type="button"
                data-testid={`signal-platform-${p}`}
                onClick={() => setPlatform(p)}
                className={
                  "mono text-[10.5px] px-2.5 py-1 rounded-full border transition-colors duration-150 tracking-tight " +
                  (platform === p
                    ? "bg-[rgba(75,107,111,0.10)] border-[rgba(75,107,111,0.30)] text-[#4b6b6f]"
                    : "bh-hairline text-[var(--bh-ink-mute)] hover:text-[var(--bh-ink)] hover:bg-[var(--bh-surface-2)]/70")
                }
              >
                {p === "all" ? "All platforms" : p}
              </button>
            ))}
          </section>
        )}

        {items === null ? (
          <div className="bh-surface rounded p-12 text-center text-neutral-500 text-sm">
            Loading signals…
          </div>
        ) : visible.length === 0 ? (
          <div
            data-testid="signals-empty"
            className="bh-surface rounded p-10 border-t border-t-sky-500/60 space-y-3"
          >
            <div className="flex items-center gap-2 text-neutral-300">
              <Sparkles size={14} className="text-sky-300" />
              <span className="font-display text-lg font-semibold">
                No non-permit signals yet.
              </span>
            </div>
            <p className="text-sm text-neutral-500 max-w-lg leading-relaxed">
              Every current lead in Airtable is permit-sourced. Non-permit
              signals will surface here the moment your automation writes any
              of:
            </p>
            <ul className="mono text-[11px] uppercase tracking-widest text-neutral-500 space-y-1 pl-1">
              <li>· Source = Website / Referral / Nextdoor / Google Places / Social / …</li>
              <li>· Source category = anything other than &quot;Permit&quot;</li>
            </ul>
            <div className="inline-flex items-center gap-2 mono text-[10px] uppercase tracking-widest text-neutral-500 border bh-hairline rounded px-2 py-1">
              <AlertTriangle size={10} /> A public signal is not permission to contact
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            {visible.map((s) => (
              <SignalRow key={s.id} s={s} />
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

export default NonPermitSignals;
