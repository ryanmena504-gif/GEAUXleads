import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import TopHeader from "@/components/TopHeader";
import LearningStrip from "@/components/LearningStrip";
import MorningBrief from "@/components/MorningBrief";
import { api } from "@/lib/api";
import { useLiveUpdates } from "@/hooks/useLiveUpdates";
import { fmtMoney, moneyDisplay, sourceLabel } from "@/lib/formatters";
import {
  queueBucket,
  sortForQueue,
  allowedAction,
  whyReady,
  notReadyReason,
} from "@/lib/queue";
import useUserSettings from "@/hooks/useUserSettings";
import {
  Mail,
  Reply,
  Info,
  ChevronRight,
  MapPin,
  Phone,
  Sparkles,
  Clock,
  ExternalLink,
} from "lucide-react";

// Short hostname for source-URL chips (e.g. "onestop.nola.gov" → "nola.gov").
const shortHost = (url) => {
  try {
    const h = new URL(url).hostname.replace(/^www\./, "");
    const parts = h.split(".");
    return parts.length >= 3 ? parts.slice(-2).join(".") : h;
  } catch {
    return null;
  }
};

/**
 * SourceChip — one-tap link to the origin of a lead (permit filing, listing,
 * post, etc.). Rendered on Ready to Contact rows so the operator can verify
 * the source in a single tap. Purely a navigation link — no state changes,
 * no backend write.
 */
const SourceChip = ({ opp }) => {
  const url = opp?.source_url;
  if (!url) return null;
  const host = shortHost(url);
  const label = host || sourceLabel(opp.source) || "Source";
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      data-testid={`source-chip-${opp.id}`}
      onClick={(e) => e.stopPropagation()}
      className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md text-[12px] font-medium border bh-hairline text-[var(--bh-ink-2)] hover:text-[var(--bh-ink)] hover:bg-white/[0.03] transition-colors"
      title={url}
    >
      <ExternalLink size={12} strokeWidth={1.75} />
      <span className="mono uppercase tracking-widest text-[10px] opacity-75">Source</span>
      <span className="truncate max-w-[180px]">{label}</span>
    </a>
  );
};

// ─── mailto helpers ───────────────────────────────────────────────────────
// Draft-only. Opening a draft NEVER writes to Airtable. Ryan chooses whether
// to press Send inside his native mail app.

const enc = encodeURIComponent;

const buildFirstDraft = (opp, sender) => {
  const first = (opp.opportunity_name || opp.name || "there").split(" ")[0];
  const subject = opp.first_message_subject || `Quick note about ${opp.project_type || "your project"}`;
  const bodyLines = [
    `Hi ${opp.decision_maker || first},`,
    "",
    opp.first_message ||
      opp.first_contact_message ||
      "I came across your recent project and thought I could help.",
    "",
    sender?.sender_name ? `— ${sender.sender_name}` : "— Ryan",
    sender?.sender_phone ? sender.sender_phone : "",
  ]
    .filter(Boolean)
    .join("\n");
  return { subject, body: bodyLines };
};

const buildFollowUpDraft = (opp, sender) => {
  const first = (opp.opportunity_name || opp.name || "there").split(" ")[0];
  const subject = `Following up · ${opp.project_type || opp.name || "your project"}`;
  const rec = opp.current_recommendation || "Just checking in to see if now is a better time to chat.";
  const bodyLines = [
    `Hi ${opp.decision_maker || first},`,
    "",
    rec,
    "",
    sender?.sender_name ? `— ${sender.sender_name}` : "— Ryan",
    sender?.sender_phone ? sender.sender_phone : "",
  ]
    .filter(Boolean)
    .join("\n");
  return { subject, body: bodyLines };
};

// ─── UI atoms ─────────────────────────────────────────────────────────────

const Chip = ({ label, value, tone = "neutral" }) => {
  const styles =
    tone === "ready"
      ? { bg: "rgba(214,175,54,0.08)", fg: "var(--bh-brass)", border: "var(--bh-hair-warm)" }
      : tone === "warn"
        ? { bg: "rgba(214,175,54,0.05)", fg: "var(--bh-brass-2)", border: "var(--bh-hair-warm)" }
        : { bg: "var(--bh-surface-2)", fg: "var(--bh-ink-mute)", border: "var(--bh-hair)" };
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-medium tracking-tight"
      style={{ background: styles.bg, color: styles.fg, borderColor: styles.border }}
    >
      <span className="text-[9.5px] uppercase tracking-widest opacity-75">{label}</span>
      <span>{value}</span>
    </span>
  );
};

const EmptyCard = ({ children, testId }) => (
  <div
    data-testid={testId}
    className="bh-surface rounded-md p-6 text-center text-sm text-[var(--bh-ink-mute)]"
  >
    {children}
  </div>
);

// ─── Row variants ─────────────────────────────────────────────────────────

const HeaderMeta = ({ opp }) => (
  <div className="mt-1 flex items-center gap-3 text-[12.5px] text-[var(--bh-ink-mute)] flex-wrap">
    {opp.project_address && (
      <span className="inline-flex items-center gap-1.5">
        <MapPin size={11} strokeWidth={1.75} />
        {opp.project_address}
      </span>
    )}
    {opp.project_type && <span>· {opp.project_type}</span>}
    {opp.source && <span>· Found on {sourceLabel(opp.source)}</span>}
  </div>
);

/**
 * ReadyRow — Ready to Contact. Shows governed signals, Priority Explanation
 * (Why This Matters), Current Recommendation (What to Do Next), and a single
 * "Open Email Draft" (or "Open Text Draft" when SMS Permission is granted
 * and no public email is on file).
 */
const ReadyRow = ({ opp, sender }) => {
  const chips = whyReady(opp);
  const action = allowedAction(opp);
  const email = opp.email || opp.email_alt;

  const onEmailDraft = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!email) return;
    const draft = buildFirstDraft(opp, sender);
    window.location.href = `mailto:${enc(email)}?subject=${enc(draft.subject)}&body=${enc(draft.body)}`;
  };

  return (
    <div
      data-testid={`ready-row-${opp.id}`}
      className="bh-surface rounded-md p-4 border-l-2"
      style={{ borderLeftColor: "var(--bh-brass)" }}
    >
      <div className="flex items-start justify-between gap-4">
        <Link to={`/opportunities/${opp.id}`} className="flex-1 min-w-0 group">
          <div className="font-display text-[17px] text-[var(--bh-ink)] group-hover:text-white tracking-tight truncate">
            {opp.name}
          </div>
          <HeaderMeta opp={opp} />
          {opp.priority_explanation && (
            <div className="mt-2 text-[13px] text-[var(--bh-ink-2)]">
              <span className="bh-eyebrow mr-2">Why this matters</span>
              {opp.priority_explanation}
            </div>
          )}
          {opp.current_recommendation && (
            <div className="mt-1.5 text-[13px] text-amber-200/90">
              <span className="bh-eyebrow mr-2">What to do next</span>
              {opp.current_recommendation}
            </div>
          )}
          {opp.project_fit_reason && (
            <div className="mt-1.5 text-[12.5px] text-[var(--bh-ink-3)]">
              <span className="bh-eyebrow mr-2">Fit reason</span>
              {opp.project_fit_reason}
            </div>
          )}
          {chips.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {chips.map((c) => (
                <Chip key={c.label} label={c.label} value={c.value} tone="ready" />
              ))}
              {typeof opp.governed_priority_score === "number" && (
                <Chip label="Score" value={opp.governed_priority_score} tone="ready" />
              )}
            </div>
          )}
          {opp.public_contact_evidence && (
            <details className="mt-2 group/details">
              <summary className="cursor-pointer text-[11.5px] text-[var(--bh-ink-3)] hover:text-[var(--bh-ink)] inline-flex items-center gap-1">
                <Info size={11} /> More details · public contact evidence
              </summary>
              <div className="mt-2 text-[12px] text-[var(--bh-ink-3)] leading-relaxed pl-4 border-l bh-hairline">
                <div>{opp.public_contact_evidence}</div>
                {opp.contact_verified_date && (
                  <div className="mt-1 mono text-[10.5px] uppercase tracking-widest opacity-75">
                    Verified {opp.contact_verified_date}
                  </div>
                )}
                {opp.score_basis && (
                  <div className="mt-2 pt-2 border-t bh-hairline">
                    <div className="mono text-[10px] uppercase tracking-widest opacity-75 mb-0.5">
                      Score basis
                    </div>
                    <div>{opp.score_basis}</div>
                  </div>
                )}
              </div>
            </details>
          )}
        </Link>
        {(() => {
          const money = moneyDisplay(opp);
          return money ? (
            <div className="hidden md:block text-right shrink-0">
              <div className="bh-eyebrow">Possible work value</div>
              <div
                className="font-display text-[18px] text-[var(--bh-ink)] tabular-nums"
                data-testid={`money-${opp.id}`}
              >
                {money}
              </div>
            </div>
          ) : null;
        })()}
      </div>

      <div className="mt-3 pt-3 border-t bh-hairline flex flex-wrap items-center gap-2">
        <SourceChip opp={opp} />
        {action === "email_first" && email && (
          <button
            type="button"
            data-testid={`email-now-${opp.id}`}
            onClick={onEmailDraft}
            className="inline-flex items-center gap-1.5 h-9 px-4 rounded-md text-[13px] font-semibold"
            style={{ background: "var(--bh-brass)", color: "var(--bh-surface)" }}
          >
            <Mail size={13} /> Email Now
          </button>
        )}
        {!action && (
          <span className="text-[11.5px] text-[var(--bh-ink-3)]">
            No verified public business email on file — open the record to add one.
          </span>
        )}
        <Link
          to={`/opportunities/${opp.id}`}
          className="ml-auto text-[12px] text-[var(--bh-ink-3)] hover:text-[var(--bh-ink)] inline-flex items-center gap-1"
        >
          Open <ChevronRight size={12} />
        </Link>
      </div>
    </div>
  );
};

/**
 * ContactedRow — a lead Ryan has already reached out to. NEVER shows a
 * first-contact action. Follow-up draft only.
 */
const ContactedRow = ({ opp, sender }) => {
  const email = opp.email || opp.email_alt;
  const action = allowedAction(opp);

  const onFollowUp = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (action !== "email_followup" || !email) return;
    const draft = buildFollowUpDraft(opp, sender);
    window.location.href = `mailto:${enc(email)}?subject=${enc(draft.subject)}&body=${enc(draft.body)}`;
  };

  return (
    <div
      data-testid={`contacted-row-${opp.id}`}
      className="bh-surface rounded-md p-4"
    >
      <div className="flex items-start justify-between gap-4">
        <Link to={`/opportunities/${opp.id}`} className="flex-1 min-w-0 group">
          <div className="font-display text-[17px] text-[var(--bh-ink)] group-hover:text-white tracking-tight truncate">
            {opp.name}
          </div>
          <HeaderMeta opp={opp} />
          <div className="mt-2 flex flex-wrap gap-1.5">
            {opp.contact_state && <Chip label="Status" value={opp.contact_state} />}
            {opp.freshness && <Chip label="Freshness" value={opp.freshness} />}
            {opp.next_follow_up && (
              <Chip label="Next follow-up" value={opp.next_follow_up} />
            )}
          </div>
          {opp.current_recommendation && (
            <div className="mt-2 text-[13px] text-amber-200/90">
              <span className="bh-eyebrow mr-2">What to do next</span>
              {opp.current_recommendation}
            </div>
          )}
          {opp.reply_summary && (
            <div className="mt-1.5 text-[12.5px] text-[var(--bh-ink-3)] line-clamp-2">
              <span className="bh-eyebrow mr-2">Last reply</span>
              {opp.reply_summary}
            </div>
          )}
        </Link>
      </div>
      <div className="mt-3 pt-3 border-t bh-hairline flex flex-wrap items-center gap-2">
        {action === "email_followup" && (
          <button
            type="button"
            data-testid={`follow-up-email-${opp.id}`}
            onClick={onFollowUp}
            className="inline-flex items-center gap-1.5 h-9 px-4 rounded-md text-[13px] font-semibold border bh-hairline text-[var(--bh-ink)] hover:bg-[var(--bh-surface-2)]"
          >
            <Reply size={13} /> Follow Up Email
          </button>
        )}
        {!action && (
          <span className="text-[11.5px] text-[var(--bh-ink-3)]">
            No verified public business email on file — open the record for details.
          </span>
        )}
        <Link
          to={`/opportunities/${opp.id}`}
          className="ml-auto text-[12px] text-[var(--bh-ink-3)] hover:text-[var(--bh-ink)] inline-flex items-center gap-1"
        >
          Open <ChevronRight size={12} />
        </Link>
      </div>
    </div>
  );
};

/**
 * AllProjectsRow — no messaging controls of any kind. Shows why the
 * record is NOT ready (from Contact Readiness governed field).
 */
const AllProjectsRow = ({ opp }) => {
  const reason = notReadyReason(opp);
  return (
    <Link
      to={`/opportunities/${opp.id}`}
      data-testid={`all-row-${opp.id}`}
      className="block bh-surface rounded-md p-4 transition-colors duration-150 hover:bg-white/[0.03]"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="font-display text-[16px] text-[var(--bh-ink)] tracking-tight truncate">
            {opp.name}
          </div>
          <HeaderMeta opp={opp} />
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Chip label="Reason" value={reason} tone="warn" />
            {opp.freshness && <Chip label="Freshness" value={opp.freshness} />}
            {opp.evidence_status && <Chip label="Evidence" value={opp.evidence_status} />}
          </div>
          {opp.current_recommendation && (
            <div className="mt-2 text-[12.5px] text-[var(--bh-ink-3)] line-clamp-2">
              <span className="bh-eyebrow mr-2">Recommendation</span>
              {opp.current_recommendation}
            </div>
          )}
        </div>
        <div className="text-right shrink-0">
          {typeof opp.governed_priority_score === "number" && (
            <div className="text-[10.5px] mono uppercase tracking-widest text-[var(--bh-ink-3)]">
              Score {opp.governed_priority_score}
            </div>
          )}
        </div>
      </div>
    </Link>
  );
};

// ─── Section shell ────────────────────────────────────────────────────────

const SectionShell = ({ eyebrow, title, hint, icon: Icon, count, testId, children }) => (
  <section data-testid={testId} className="space-y-3">
    <div>
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
    {children}
  </section>
);

// ─── Page ─────────────────────────────────────────────────────────────────

const CommandCenter = () => {
  const [items, setItems] = useState(null);
  const { settings: senderSettings } = useUserSettings();

  const load = useCallback(() => {
    api.listOpportunities().then(setItems).catch(() => setItems([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);
  useLiveUpdates(load);

  const { ready, contacted, all } = useMemo(() => {
    if (!Array.isArray(items)) return { ready: null, contacted: null, all: null };
    const readyList = [];
    const contactedList = [];
    const allList = [];
    for (const opp of items) {
      const bucket = queueBucket(opp);
      if (bucket === "ready") readyList.push(opp);
      else if (bucket === "contacted") contactedList.push(opp);
      else allList.push(opp);
    }
    return {
      ready: sortForQueue(readyList),
      contacted: sortForQueue(contactedList),
      all: sortForQueue(allList),
    };
  }, [items]);

  return (
    <>
      <TopHeader
        pageTitle="Your work list"
        subtitle="Ready to Contact first. Contacted for follow-ups. All Projects for everything else."
      />
      <main className="px-4 lg:px-8 py-6 pb-28 max-w-6xl space-y-10">
        <MorningBrief />
        <LearningStrip />
        <SectionShell
          testId="section-ready-to-contact"
          eyebrow="1 · Ready to Contact"
          title="Ready to Contact"
          hint="Records the classifier has approved for first contact — verified public business channel, premium fit, and evidence on file. Only list that allows a first-contact action."
          icon={Mail}
          count={ready?.length}
        >
          {ready === null ? (
            <EmptyCard testId="ready-loading">Loading…</EmptyCard>
          ) : ready.length === 0 ? (
            <EmptyCard testId="ready-empty">
              No records are Ready to Contact yet. The classifier will promote
              them here once every gate passes.
            </EmptyCard>
          ) : (
            <div className="space-y-2">
              {ready.map((opp) => (
                <ReadyRow key={opp.id} opp={opp} sender={senderSettings} />
              ))}
            </div>
          )}
        </SectionShell>

        <SectionShell
          testId="section-contacted"
          eyebrow="2 · Contacted"
          title="Contacted"
          hint="Records already reached out to. Follow-up drafts only — no first-contact actions here."
          icon={Reply}
          count={contacted?.length}
        >
          {contacted === null ? (
            <EmptyCard testId="contacted-loading">Loading…</EmptyCard>
          ) : contacted.length === 0 ? (
            <EmptyCard testId="contacted-empty">
              Nothing to follow up on yet.
            </EmptyCard>
          ) : (
            <div className="space-y-2">
              {contacted.map((opp) => (
                <ContactedRow key={opp.id} opp={opp} sender={senderSettings} />
              ))}
            </div>
          )}
        </SectionShell>

        <SectionShell
          testId="section-all-projects"
          eyebrow="3 · All Projects"
          title="All Projects"
          hint="Everything else — paused, needs proof, needs public contact, needs history check, or not appropriate. Read-only view. No outreach actions."
          icon={Clock}
          count={all?.length}
        >
          {all === null ? (
            <EmptyCard testId="all-loading">Loading…</EmptyCard>
          ) : all.length === 0 ? (
            <EmptyCard testId="all-empty">Every record is in Ready or Contacted.</EmptyCard>
          ) : (
            <div className="space-y-1.5">
              {all.slice(0, 40).map((opp) => (
                <AllProjectsRow key={opp.id} opp={opp} />
              ))}
              {all.length > 40 && (
                <div className="pt-2 text-[12px] text-[var(--bh-ink-3)]">
                  Showing 40 of {all.length}. Open All Projects to see more.
                </div>
              )}
            </div>
          )}
        </SectionShell>
      </main>
    </>
  );
};

export default CommandCenter;
