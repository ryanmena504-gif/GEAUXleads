import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import TopHeader from "@/components/TopHeader";
import ContactBadge from "@/components/ContactBadge";
import DraftNoteDrawer from "@/components/DraftNoteDrawer";
import OpenInMessages from "@/components/OpenInMessages";
import { PriorityBand } from "@/components/PriorityBadge";
import { contactState } from "@/lib/priority";
import { api } from "@/lib/api";
import { useLiveUpdates } from "@/hooks/useLiveUpdates";
import { outreachAllowed } from "@/lib/queue";
import {
  ExternalLink,
  Globe,
  Handshake,
  Instagram,
  MapPin,
  PhoneCall,
} from "lucide-react";

const normalizeCompany = (value) =>
  String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

const projectMatchesFor = (partner, allItems) => {
  const key = normalizeCompany(partner.company);
  if (!key) return [];
  return allItems.filter(
    (item) =>
      item.id !== partner.id &&
      item.lane !== "partner" &&
      normalizeCompany(item.company) === key,
  );
};

const PublicLinks = ({ person }) => {
  const links = [
    { label: "Website", url: person.contact_website || person.website, icon: Globe },
    { label: "Instagram", url: person.contact_instagram || person.instagram, icon: Instagram },
    { label: "Public record", url: person.source_url, icon: ExternalLink },
  ].filter((link) => link.url);

  if (!links.length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-x-3 gap-y-2">
      {links.map(({ label, url, icon: Icon }) => (
        <a
          key={`${label}-${url}`}
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          data-testid={`partner-link-${label.toLowerCase()}-${person.id}`}
          className="inline-flex items-center gap-1 text-[12px] text-sky-300 hover:text-sky-200"
        >
          <Icon size={12} /> {label}
        </a>
      ))}
    </div>
  );
};

const PartnerCard = ({ person, linkedProjects, onDraft }) => {
  return (
    <article
      data-testid={`partner-row-${person.id}`}
      className="bh-surface rounded-md p-5 border-t border-t-emerald-500/50"
    >
      <div className="flex items-start gap-4">
        <div className="hidden sm:flex w-[110px] shrink-0 flex-col gap-2 pt-0.5">
          {/* A "Not a fit" record gets no priority badge — the two contradict. */}
          {contactState(person).key !== "not_fit" && (
            <PriorityBand band={person.priority_band} score={person.priority_score} />
          )}
          <ContactBadge opportunity={person} />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Link
              to={`/opportunities/${person.id}`}
              data-testid={`partner-open-${person.id}`}
              className="font-display text-[18px] font-semibold tracking-tight text-[var(--bh-ink)] hover:text-amber-300"
            >
              {person.name || person.company || "Unnamed business"}
            </Link>
            {person.company && person.company !== person.name && (
              <span className="text-[12px] text-[var(--bh-ink-mute)]">{person.company}</span>
            )}
          </div>

          <div className="mt-1 flex flex-wrap items-center gap-3 text-[12px] text-[var(--bh-ink-mute)]">
            {person.project_type && <span>{person.project_type}</span>}
            {person.project_address && (
              <span className="inline-flex items-center gap-1">
                <MapPin size={12} /> {person.project_address}
              </span>
            )}
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div>
              <div className="bh-eyebrow">Why this matters</div>
              <p className="mt-1 text-sm leading-relaxed text-[var(--bh-ink-2)]">
                {person.recommendation_reason || person.evidence_summary || "Public business record saved for review."}
              </p>
            </div>
            <div>
              <div className="bh-eyebrow">Public project connection</div>
              {linkedProjects.length ? (
                <div className="mt-1 text-sm leading-relaxed text-[var(--bh-ink-2)]">
                  {linkedProjects.length} public project{linkedProjects.length === 1 ? "" : "s"} tied to
                  this exact company name:
                  <div className="mt-1 flex flex-wrap gap-x-2 gap-y-1">
                    {linkedProjects.slice(0, 3).map((project) => (
                      <Link
                        key={project.id}
                        to={`/opportunities/${project.id}`}
                        className="text-sky-300 hover:text-sky-200"
                      >
                        {project.name}
                      </Link>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="mt-1 text-sm leading-relaxed text-[var(--bh-ink-3)]">
                  No exact company-to-project match has been saved yet. This stays a business
                  relationship to watch, not a claimed job connection.
                </p>
              )}
            </div>
          </div>

          {person.recommended_action || person.next_best_action ? (
            <div className="mt-3 rounded-md bg-[var(--bh-surface-2)] px-3 py-2 text-[13px] text-[var(--bh-ink-2)]">
              <span className="bh-eyebrow mr-2">What to do next</span>
              {person.recommended_action || person.next_best_action}
            </div>
          ) : null}

          <PublicLinks person={person} />

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <div className="sm:hidden">
              <ContactBadge opportunity={person} />
            </div>
            {(() => {
              const mode = outreachAllowed(person);
              // All Projects (or unclassified): show the governed reason and
              // NO messaging or draft controls. This is the fix for the
              // Greige Interiors leak — Contacted records also route here.
              if (mode === "none") {
                return (
                  <span
                    data-testid={`partner-no-outreach-${person.id}`}
                    className="inline-flex items-center gap-1.5 rounded-full border bh-hairline px-2.5 py-1 text-[11px] text-[var(--bh-ink-mute)]"
                  >
                    <PhoneCall size={11} />
                    {person.contact_readiness || "Not classified for outreach yet"}
                  </span>
                );
              }
              // Ready or Contacted: the OpenInMessages component itself is
              // strictly gated by outreachAllowed(), so pill mode renders the
              // right buttons (Email + Text for Ready; single Follow-Up for
              // Contacted) or nothing when no channel is on file.
              return <OpenInMessages opportunity={person} variant="pill" />;
            })()}
            {/* Draft-a-note retired app-wide. Email Now / Follow Up Email
                inside OpenInMessages is the single outreach entry point. */}
          </div>
        </div>
      </div>
    </article>
  );
};

const PartnerIntelligence = () => {
  const [items, setItems] = useState(null);
  const [draftOpp, setDraftOpp] = useState(null);

  const load = useCallback(() => {
    api.listOpportunities().then(setItems).catch(() => setItems([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);
  useLiveUpdates(load);

  const partners = useMemo(
    () =>
      (items || [])
        .filter((item) => item.lane === "partner")
        .sort((a, b) => (b.priority_score || 0) - (a.priority_score || 0)),
    [items],
  );

  return (
    <>
      <TopHeader
        pageTitle="People to Know"
        subtitle="Business relationships that may bring repeat work."
      />
      <main className="px-4 lg:px-8 py-6 pb-28 max-w-6xl space-y-5">
        <section
          data-testid="partner-hero"
          className="bh-surface rounded-md p-5 border-t border-t-emerald-500/60"
        >
          <div className="bh-eyebrow inline-flex items-center gap-1.5">
            <Handshake size={12} /> Relationship map
          </div>
          <h2 className="mt-2 font-display text-xl font-semibold tracking-tight text-[var(--bh-ink)]">
            People, proof, and the next step in one place.
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--bh-ink-3)]">
            GEAUXleads only shows a project connection when the exact public business name
            matches a saved public project record. A public website or social link stays visible
            so you can judge the fit yourself.
          </p>
        </section>

        {items === null ? (
          <div className="bh-surface rounded-md p-8 text-sm text-[var(--bh-ink-mute)]">
            Loading people to know…
          </div>
        ) : partners.length ? (
          <div className="space-y-3">
            {partners.map((person) => (
              <PartnerCard
                key={person.id}
                person={person}
                linkedProjects={projectMatchesFor(person, items)}
                onDraft={setDraftOpp}
              />
            ))}
          </div>
        ) : (
          <div
            data-testid="partner-empty"
            className="bh-surface rounded-md p-8 text-sm text-[var(--bh-ink-mute)]"
          >
            No business partners are ready to review yet.
          </div>
        )}

        <DraftNoteDrawer
          open={Boolean(draftOpp)}
          onOpenChange={(open) => !open && setDraftOpp(null)}
          opportunity={draftOpp}
        />
      </main>
    </>
  );
};

export default PartnerIntelligence;
