import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import TopHeader from "@/components/TopHeader";
import OpportunityRow from "@/components/OpportunityRow";
import WonThisMonth from "@/components/WonThisMonth";
import { PriorityBand } from "@/components/PriorityBadge";
import { api } from "@/lib/api";
import { useLiveUpdates } from "@/hooks/useLiveUpdates";
import { contactReady, isClosedOrBlocked } from "@/lib/priority";
import {
  Phone,
  Eye,
  Ban,
  ChevronRight,
  MapPin,
} from "lucide-react";

// Won leads are excluded from every visible bucket — they're a positive
// closed state that lives in the KPI strip only.
const priorityRank = (opp) =>
  typeof opp.priority_score === "number" ? opp.priority_score : -1;

const SectionShell = ({ eyebrow, title, hint, icon: Icon, count, children, testId }) => (
  <section data-testid={testId} className="space-y-3">
    <div className="flex items-baseline justify-between gap-3">
      <div className="min-w-0">
        <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 flex items-center gap-1.5">
          {Icon ? <Icon size={11} strokeWidth={1.75} /> : null}
          {eyebrow}
        </div>
        <h2 className="font-display text-[22px] text-[var(--bh-ink)] tracking-tight">
          {title}
          {typeof count === "number" && (
            <span className="ml-2 text-[13px] text-[var(--bh-ink-mute)] tabular-nums">
              ({count})
            </span>
          )}
        </h2>
        {hint && (
          <p className="text-[12.5px] text-[var(--bh-ink-mute)] mt-0.5 max-w-2xl leading-relaxed">
            {hint}
          </p>
        )}
      </div>
    </div>
    {children}
  </section>
);

const EmptyCard = ({ children, testId }) => (
  <div
    data-testid={testId}
    className="bh-surface rounded-md p-6 text-center text-sm text-[var(--bh-ink-mute)]"
  >
    {children}
  </div>
);

const WatchRow = ({ opp }) => {
  const outreach = String(opp.outreach_status || "").toLowerCase();
  const notes = String(opp.notes || "");
  const noContactYet =
    notes.toLowerCase().includes("no public business contact found") ||
    (!opp.phone && !opp.email);
  const pillLabel = noContactYet ? "No public business contact yet" : "Watching";
  const pillStyle = noContactYet
    ? { bg: "var(--bh-brass-mute)", fg: "var(--bh-brass)", border: "var(--bh-hair-warm)" }
    : { bg: "var(--bh-surface-2)", fg: "var(--bh-ink-mute)", border: "var(--bh-hair)" };
  return (
    <Link
      to={`/opportunities/${opp.id}`}
      data-testid={`watch-row-${opp.id}`}
      className="block bh-surface rounded-md p-4 transition-colors duration-150 hover:bg-white/[0.03]"
    >
      <div className="flex items-start gap-4">
        <div className="hidden sm:flex flex-col items-start pt-1 w-[130px] shrink-0 gap-2">
          <PriorityBand band={opp.priority_band} score={opp.priority_score} />
          <span
            className="text-[10.5px] px-2 py-0.5 rounded-full border font-medium tracking-tight"
            style={{ background: pillStyle.bg, borderColor: pillStyle.border, color: pillStyle.fg }}
          >
            {pillLabel}
          </span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-display text-[17px] text-[var(--bh-ink)] truncate tracking-tight">
            {opp.name}
          </div>
          <div className="mt-1 flex items-center gap-3 text-[12.5px] text-[var(--bh-ink-mute)] flex-wrap">
            {opp.project_address && (
              <span className="inline-flex items-center gap-1.5">
                <MapPin size={11} strokeWidth={1.75} />
                {opp.project_address}
              </span>
            )}
            {opp.project_type && <span>· {opp.project_type}</span>}
          </div>
          {opp.recommendation_reason && (
            <div className="mt-2 text-[13px] text-[var(--bh-ink-2)] line-clamp-2">
              <span className="bh-eyebrow mr-2">Why this matters</span>
              {opp.recommendation_reason}
            </div>
          )}
          <div className="mt-3 text-[12.5px] text-amber-200/90">
            Open for details →
          </div>
        </div>
      </div>
    </Link>
  );
};

const NotFitRow = ({ opp }) => {
  let label = "Not a fit";
  const status = String(opp.status || "").toLowerCase();
  const outreach = String(opp.outreach_status || "").toLowerCase();
  if (status.includes("disqualified")) label = "Disqualified";
  else if (status.includes("lost")) label = "Lost";
  else if (outreach.includes("do not contact")) label = "Do not contact";
  else if (outreach.includes("not interested")) label = "Not interested";
  return (
    <Link
      to={`/opportunities/${opp.id}`}
      data-testid={`notfit-row-${opp.id}`}
      className="block bh-surface rounded-md p-3 transition-colors duration-150 hover:bg-white/[0.03]"
    >
      <div className="flex items-start gap-4">
        <span
          className="hidden sm:inline-flex items-center gap-1.5 text-[10.5px] px-2 py-0.5 rounded-full border font-medium tracking-tight shrink-0 mt-1"
          style={{
            background: "var(--bh-clay-mute, rgba(165,90,62,0.08))",
            color: "var(--bh-clay, #a55a3e)",
            borderColor: "rgba(165,90,62,0.28)",
          }}
        >
          <Ban size={10} strokeWidth={1.75} /> {label}
        </span>
        <div className="flex-1 min-w-0">
          <div className="font-medium text-[var(--bh-ink)] truncate">
            {opp.name}
          </div>
          <div className="mt-0.5 text-[12px] text-[var(--bh-ink-mute)] truncate">
            {opp.project_type ? `${opp.project_type} · ` : ""}
            {opp.project_address || "—"}
          </div>
        </div>
      </div>
    </Link>
  );
};

const CommandCenter = () => {
  const [opps, setOpps] = useState(null);

  const load = useCallback(() => {
    api
      .listOpportunities({ sort: "lead_score" })
      .then(setOpps)
      .catch(() => setOpps([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useLiveUpdates(useCallback(() => load(), [load]));

  const { contactNow, watchList, notFitList } = useMemo(() => {
    const items = Array.isArray(opps) ? opps : [];
    const now = [];
    const watch = [];
    const notFit = [];

    for (const o of items) {
      const status = String(o.status || "").toLowerCase();
      // Won leads live only in the KPI strip.
      if (status.includes("won")) continue;
      if (isClosedOrBlocked(o)) {
        notFit.push(o);
        continue;
      }
      if (contactReady(o).ready) {
        now.push(o);
        continue;
      }
      // Everything else that's still active belongs in Watch — including
      // records enrichment couldn't find a public business contact for yet.
      watch.push(o);
    }

    now.sort((a, b) => priorityRank(b) - priorityRank(a));
    watch.sort((a, b) => priorityRank(b) - priorityRank(a));
    notFit.sort((a, b) => (b.last_reviewed || "").localeCompare(a.last_reviewed || ""));

    return { contactNow: now, watchList: watch, notFitList: notFit };
  }, [opps]);

  return (
    <>
      <TopHeader
        pageTitle="Today"
        subtitle="Three lists: who to reach out to, what to watch, and what to leave alone"
      />

      <div className="px-5 lg:px-10 py-8 space-y-10">
        {/* KPI hero — quick pulse of the business, not a work bucket */}
        <WonThisMonth />

        {/* Bucket 1 — Contact Now */}
        <SectionShell
          testId="section-contact-now"
          eyebrow="1 · Contact Now"
          title="Contact Now"
          hint="Verified public business phone or email · premium fit · source URL and date checked · no outreach conflict. Tap a card to open a draft on your phone — you press Send when you're ready."
          icon={Phone}
          count={contactNow.length}
        >
          {opps === null ? (
            <EmptyCard testId="contact-loading">Loading…</EmptyCard>
          ) : contactNow.length === 0 ? (
            <EmptyCard testId="contact-empty">
              Nothing meets the Contact Now bar right now. Everything active
              is in Watch below.
            </EmptyCard>
          ) : (
            <div className="space-y-2">
              {contactNow.slice(0, 10).map((o) => (
                <OpportunityRow key={o.id} opp={o} />
              ))}
              {contactNow.length > 10 && (
                <div className="pt-2">
                  <Link
                    to="/opportunities?status=Ready"
                    data-testid="contact-see-all"
                    className="text-[12.5px] text-[var(--bh-brass)] hover:text-[var(--bh-brass-2)] inline-flex items-center gap-1"
                  >
                    See all {contactNow.length} <ChevronRight size={13} />
                  </Link>
                </div>
              )}
            </div>
          )}
        </SectionShell>

        {/* Bucket 2 — Watch */}
        <SectionShell
          testId="section-watch"
          eyebrow="2 · Watch"
          title="Watch"
          hint="Active leads that don't yet meet the Contact Now bar — usually because a verified public business phone or email is still missing. Nothing here is ever dropped."
          icon={Eye}
          count={watchList.length}
        >
          {opps === null ? (
            <EmptyCard testId="watch-loading">Loading…</EmptyCard>
          ) : watchList.length === 0 ? (
            <EmptyCard testId="watch-empty">
              Nothing to watch right now.
            </EmptyCard>
          ) : (
            <div className="space-y-2">
              {watchList.slice(0, 15).map((o) => (
                <WatchRow key={o.id} opp={o} />
              ))}
              {watchList.length > 15 && (
                <div className="pt-2">
                  <Link
                    to="/opportunities"
                    data-testid="watch-see-all"
                    className="text-[12.5px] text-[var(--bh-brass)] hover:text-[var(--bh-brass-2)] inline-flex items-center gap-1"
                  >
                    See all {watchList.length} <ChevronRight size={13} />
                  </Link>
                </div>
              )}
            </div>
          )}
        </SectionShell>

        {/* Bucket 3 — Not a Fit */}
        <SectionShell
          testId="section-not-a-fit"
          eyebrow="3 · Not a Fit"
          title="Not a Fit"
          hint="Records marked Disqualified, Lost, Do Not Contact, or Not Interested. Kept visible so nothing is forgotten — never contacted."
          icon={Ban}
          count={notFitList.length}
        >
          {opps === null ? (
            <EmptyCard testId="notfit-loading">Loading…</EmptyCard>
          ) : notFitList.length === 0 ? (
            <EmptyCard testId="notfit-empty">
              Nothing marked Not a Fit yet.
            </EmptyCard>
          ) : (
            <div className="space-y-1.5">
              {notFitList.slice(0, 10).map((o) => (
                <NotFitRow key={o.id} opp={o} />
              ))}
              {notFitList.length > 10 && (
                <div className="pt-2">
                  <Link
                    to="/opportunities?status=Disqualified"
                    data-testid="notfit-see-all"
                    className="text-[12.5px] text-[var(--bh-brass)] hover:text-[var(--bh-brass-2)] inline-flex items-center gap-1"
                  >
                    See all {notFitList.length} <ChevronRight size={13} />
                  </Link>
                </div>
              )}
            </div>
          )}
        </SectionShell>
      </div>
    </>
  );
};

export default CommandCenter;
