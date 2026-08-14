import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import TopHeader from "@/components/TopHeader";
import OpportunityRow from "@/components/OpportunityRow";
import { api } from "@/lib/api";
import { useLiveUpdates } from "@/hooks/useLiveUpdates";
import { ArrowRight, PhoneCall, Search, Users } from "lucide-react";

const CLOSED_STATUSES = new Set(["Won", "Lost", "Disqualified"]);

const hasPublicContact = (opp) =>
  Boolean(opp?.contact_phone || opp?.phone || opp?.contact_email || opp?.email);

const sortByPriority = (items) =>
  [...items].sort((a, b) => (b.priority_score || 0) - (a.priority_score || 0));

const EmptyState = ({ children }) => (
  <div className="bh-surface rounded-md p-6 text-sm text-[var(--bh-ink-mute)]">
    {children}
  </div>
);

const HomeSection = ({ eyebrow, title, hint, icon: Icon, items, empty, to }) => (
  <section className="space-y-3">
    <div className="flex items-end justify-between gap-4">
      <div>
        <div className="bh-eyebrow inline-flex items-center gap-1.5">
          <Icon size={12} /> {eyebrow}
        </div>
        <h2 className="mt-1 font-display text-xl font-semibold tracking-tight text-[var(--bh-ink)]">
          {title}
        </h2>
        <p className="mt-1 text-sm text-[var(--bh-ink-3)]">{hint}</p>
      </div>
      {to && (
        <Link
          to={to}
          data-testid={`link-open-${eyebrow.toLowerCase().replace(/[^a-z]+/g, "-")}`}
          className="shrink-0 inline-flex items-center gap-1 text-[12px] text-[var(--bh-brass)] hover:text-[var(--bh-brass-2)]"
        >
          See all <ArrowRight size={13} />
        </Link>
      )}
    </div>

    <div className="space-y-2">
      {items === null ? (
        <EmptyState>Loading your work list…</EmptyState>
      ) : items.length ? (
        items.map((opp) => <OpportunityRow key={opp.id} opp={opp} />)
      ) : (
        <EmptyState>{empty}</EmptyState>
      )}
    </div>
  </section>
);

const CommandCenter = () => {
  const [items, setItems] = useState(null);

  const load = useCallback(() => {
    api.listOpportunities().then(setItems).catch(() => setItems([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);
  useLiveUpdates(load);

  const groups = useMemo(() => {
    if (items === null) {
      return { contactToday: null, projectsToWatch: null, peopleToKnow: null };
    }

    const active = items.filter((opp) => !CLOSED_STATUSES.has(opp.status));
    // A public phone or email makes this actionable now, regardless of whether
    // the record began life as a partner relationship or a project signal.
    // Keep the home list mutually exclusive so the same business is not shown
    // in several places at once.
    const contactToday = sortByPriority(active.filter(hasPublicContact)).slice(0, 5);
    const projectsToWatch = sortByPriority(
      active.filter((opp) => opp.lane !== "partner" && !hasPublicContact(opp)),
    ).slice(0, 5);
    const peopleToKnow = sortByPriority(
      active.filter((opp) => opp.lane === "partner" && !hasPublicContact(opp)),
    ).slice(0, 4);

    return { contactToday, projectsToWatch, peopleToKnow };
  }, [items]);

  return (
    <>
      <TopHeader
        pageTitle="Today"
        subtitle="Start with people you can actually contact. Keep the rest in view without letting it get in your way."
      />

      <main className="px-4 lg:px-8 py-6 pb-28 max-w-6xl space-y-10">
        <section
          className="bh-surface rounded-md p-5 border-t border-t-amber-500/60"
          data-testid="today-intro"
        >
          <div className="bh-eyebrow">Your simple work list</div>
          <p className="mt-2 text-[15px] leading-relaxed text-[var(--bh-ink-2)] max-w-3xl">
            Contact-ready people come first. A project without a public business phone or
            email stays in <strong className="font-medium text-[var(--bh-ink)]">Projects to Watch</strong> until there is a real way to reach the right person.
          </p>
        </section>

        <HomeSection
          eyebrow="Contact ready"
          title="People to contact today"
          hint="These have a public business phone or email. Open a draft, send it yourself, then record what happened."
          icon={PhoneCall}
          items={groups.contactToday}
          empty="Nothing is contact-ready right now. Bloodhound will keep researching public business contact details before moving anything here."
          to="/opportunities"
        />

        <HomeSection
          eyebrow="Projects to watch"
          title="Worth watching, not ready to contact"
          hint="These may be good projects, but there is no verified public business contact path yet."
          icon={Search}
          items={groups.projectsToWatch}
          empty="No projects are waiting on a public contact path."
          to="/intelligence"
        />

        <HomeSection
          eyebrow="People to know"
          title="Potential repeat-work partners"
          hint="Builders, designers, and remodelers who may send more than one job over time."
          icon={Users}
          items={groups.peopleToKnow}
          empty="No partner relationships are ready to review yet."
          to="/relationships"
        />
      </main>
    </>
  );
};

export default CommandCenter;
