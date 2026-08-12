import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import TopHeader from "@/components/TopHeader";
import OpportunityRow from "@/components/OpportunityRow";
import WonThisMonth from "@/components/WonThisMonth";
import LaneBadge from "@/components/LaneBadge";
import { PriorityBand } from "@/components/PriorityBadge";
import { api } from "@/lib/api";
import { useLiveUpdates } from "@/hooks/useLiveUpdates";
import { contactReady, hasPremiumFit } from "@/lib/priority";
import {
  Phone,
  Eye,
  Users,
  ChevronRight,
  MapPin,
} from "lucide-react";

const CLOSED_STATUSES = new Set(["Won", "Lost", "Disqualified"]);

const isActive = (opp) => !CLOSED_STATUSES.has((opp.status || "").trim());
const priorityRank = (opp) =>
  typeof opp.priority_score === "number" ? opp.priority_score : -1;

/**
 * SectionShell — plain-English section header + list body used by all three
 * Today sections. Kept tiny on purpose; the three sections are the only
 * thing on this page besides the "Won this month" strip.
 */
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

const WatchRow = ({ opp }) => (
  <Link
    to={`/opportunities/${opp.id}`}
    data-testid={`watch-row-${opp.id}`}
    className="block bh-surface rounded-md p-4 transition-colors duration-150 hover:bg-white/[0.03]"
  >
    <div className="flex items-start gap-4">
      <div className="hidden sm:flex flex-col items-start pt-1 w-[110px] shrink-0 gap-2">
        <PriorityBand band={opp.priority_band} score={opp.priority_score} />
        <span
          className="text-[10.5px] px-2 py-0.5 rounded-full border font-medium tracking-tight"
          style={{
            background: "var(--bh-brass-mute)",
            borderColor: "var(--bh-hair-warm)",
            color: "var(--bh-brass)",
          }}
        >
          Needs a phone or email
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
          Open to add a phone or email →
        </div>
      </div>
    </div>
  </Link>
);

const PartnerPreviewRow = ({ opp }) => (
  <Link
    to={`/opportunities/${opp.id}`}
    data-testid={`partner-preview-${opp.id}`}
    className="block bh-surface rounded-md p-4 transition-colors duration-150 hover:bg-white/[0.03]"
  >
    <div className="flex items-start gap-4">
      <div className="hidden sm:flex flex-col items-start pt-1 w-[110px] shrink-0 gap-2">
        <LaneBadge lane="partner" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="font-display text-[17px] text-[var(--bh-ink)] truncate tracking-tight">
          {opp.name}
        </div>
        <div className="mt-1 flex items-center gap-3 text-[12.5px] text-[var(--bh-ink-mute)] flex-wrap">
          {opp.company && <span>{opp.company}</span>}
          {opp.project_type && <span>· {opp.project_type}</span>}
        </div>
        {opp.recommendation_reason && (
          <div className="mt-2 text-[13px] text-[var(--bh-ink-2)] line-clamp-2">
            <span className="bh-eyebrow mr-2">Why they fit</span>
            {opp.recommendation_reason}
          </div>
        )}
      </div>
    </div>
  </Link>
);

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

  const { contactList, watchList, partnerList } = useMemo(() => {
    const items = Array.isArray(opps) ? opps.filter(isActive) : [];
    const contact = [];
    const watch = [];
    const partners = [];

    for (const o of items) {
      if (o.lane === "partner") {
        partners.push(o);
        continue;
      }
      const gate = contactReady(o);
      if (gate.ready) {
        contact.push(o);
      } else if (hasPremiumFit(o) && !gate.reasons.includes("blocked")) {
        watch.push(o);
      }
    }

    contact.sort((a, b) => priorityRank(b) - priorityRank(a));
    watch.sort((a, b) => priorityRank(b) - priorityRank(a));
    partners.sort((a, b) => priorityRank(b) - priorityRank(a));

    return { contactList: contact, watchList: watch, partnerList: partners };
  }, [opps]);

  return (
    <>
      <TopHeader
        pageTitle="Today"
        subtitle="Three lists: who to call, what to watch, who's on your team"
      />

      <div className="px-5 lg:px-10 py-8 space-y-10">
        {/* KPI hero — quick pulse of the business, not a section */}
        <WonThisMonth />

        {/* Section 1 — People to contact today */}
        <SectionShell
          testId="section-people-to-contact"
          eyebrow="1 · People to contact today"
          title="People to contact today"
          hint="Verified public phone or email · premium fit · everything checks out. Tap a card to open a draft on your phone — you press Send when you're ready."
          icon={Phone}
          count={contactList.length}
        >
          {opps === null ? (
            <EmptyCard testId="contact-loading">Loading…</EmptyCard>
          ) : contactList.length === 0 ? (
            <EmptyCard testId="contact-empty">
              No leads meet the strict &ldquo;contact ready&rdquo; bar right
              now. Watch the next section — projects that just need a phone or
              email get promoted the moment we find one.
            </EmptyCard>
          ) : (
            <div className="space-y-2">
              {contactList.slice(0, 10).map((o) => (
                <OpportunityRow key={o.id} opp={o} />
              ))}
              {contactList.length > 10 && (
                <div className="pt-2">
                  <Link
                    to="/opportunities?status=Ready"
                    data-testid="contact-see-all"
                    className="text-[12.5px] text-[var(--bh-brass)] hover:text-[var(--bh-brass-2)] inline-flex items-center gap-1"
                  >
                    See all {contactList.length} <ChevronRight size={13} />
                  </Link>
                </div>
              )}
            </div>
          )}
        </SectionShell>

        {/* Section 2 — Projects to watch */}
        <SectionShell
          testId="section-projects-to-watch"
          eyebrow="2 · Projects to watch"
          title="Projects to watch"
          hint="Premium fit but we don't have a verified phone or email yet. Tap a card to add contact info or add a note."
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
              {watchList.slice(0, 10).map((o) => (
                <WatchRow key={o.id} opp={o} />
              ))}
              {watchList.length > 10 && (
                <div className="pt-2">
                  <Link
                    to="/opportunities?status=Needs research"
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

        {/* Section 3 — People to know */}
        <SectionShell
          testId="section-people-to-know"
          eyebrow="3 · People to know"
          title="People to know"
          hint="Builders, designers, and remodelers worth staying in touch with. Open the full list for tabs by trade."
          icon={Users}
          count={partnerList.length}
        >
          {opps === null ? (
            <EmptyCard testId="partners-loading">Loading…</EmptyCard>
          ) : partnerList.length === 0 ? (
            <EmptyCard testId="partners-empty">
              No people to know yet. Partners show up here as soon as we find
              them.
            </EmptyCard>
          ) : (
            <div className="space-y-2">
              {partnerList.slice(0, 6).map((o) => (
                <PartnerPreviewRow key={o.id} opp={o} />
              ))}
              <div className="pt-2">
                <Link
                  to="/relationships"
                  data-testid="partners-see-all"
                  className="text-[12.5px] text-[var(--bh-brass)] hover:text-[var(--bh-brass-2)] inline-flex items-center gap-1"
                >
                  Open People to Know <ChevronRight size={13} />
                </Link>
              </div>
            </div>
          )}
        </SectionShell>
      </div>
    </>
  );
};

export default CommandCenter;
