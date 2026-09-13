import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
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
  needsEnrichment,
} from "@/lib/queue";
import useUserSettings from "@/hooks/useUserSettings";
import DaysOnTable from "@/components/DaysOnTable";
import { buildSalutation, stripLeadingGreeting } from "@/lib/greeting";
import {
  Mail,
  Reply,
  Info,
  ChevronRight,
  ChevronDown,
  MapPin,
  Phone,
  Sparkles,
  Clock,
  Snowflake,
  Zap,
  Gift,
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
  const lane = (opp.lane || "").toLowerCase();
  const isPartner = lane === "partner";
  const isLandlord = lane === "landlord";
  const senderName = sender?.sender_name || "Ryan";
  const senderPhone = sender?.sender_phone || "";
  const generic = isPartner ? "team" : "there";
  // Pass ONLY person-name fields — never opp.name (record/project name).
  const salutation = buildSalutation(
    [opp.decision_maker, opp.contact_name],
    { verb: "Hi", generic },
  );
  const partnerFallback = [
    `I'm ${senderName} with The Shirtless Handyman. I came across ${opp.name || "your team"} while looking at the kind of work being done around the area.`,
    "",
    "We handle seamless finish work when a project calls for something beyond tile or paint: microcement, lime plaster, waterproof grout-free showers, feature walls, and similar details. Not every job needs it, but it can be a strong option on the right project — happy to be a resource whenever it comes up.",
    "",
    "Would love to trade referrals or meet up for a quick coffee if you're open to it.",
  ].join("\n");
  const landlordFallback = [
    `I'm ${senderName} with The Shirtless Handyman. I saw you own ${opp.project_address || "properties around the area"} and wanted to reach out.`,
    "",
    "I'm a one-call fix. No coordinating three trades, no waiting on estimates. Text me a photo of what needs attention and I'll tell you what it'll cost and when I can be there.",
  ].join("\n");
  const projectFallback = [
    `I'm ${senderName} with The Shirtless Handyman. I came across your ${opp.project_type || "project"} and wanted to reach out.`,
    "",
    "We handle seamless finish work when a project calls for something beyond tile or paint: microcement, lime plaster, waterproof grout-free showers, feature walls, and similar details. Happy to answer any questions or share references whenever you're ready.",
  ].join("\n");
  const fallbackBody = isLandlord ? landlordFallback : (isPartner ? partnerFallback : projectFallback);
  const subject =
    opp.first_message_subject ||
    (isLandlord
      ? `Turnovers, punch-list, and everything between tenants`
      : isPartner
        ? `${senderName} at The Shirtless Handyman — quick intro`
        : `Quick note about your ${opp.project_type || "project"}`);
  // Strip any greeting the classifier already put on `first_message` so
  // we never render "Hi Tristan,\n\nHi Tristan,\nI'm Ryan..." style
  // duplicates. Fallback bodies never carry a greeting themselves.
  const rawBody =
    opp.first_message || opp.first_contact_message || fallbackBody;
  const cleanBody = stripLeadingGreeting(rawBody);
  const bodyLines = [
    salutation,
    "",
    cleanBody,
    "",
    `— ${senderName}`,
    senderPhone,
  ]
    .filter(Boolean)
    .join("\n");
  return { subject, body: bodyLines };
};

const buildFollowUpDraft = (opp, sender) => {
  const isLandlord = (opp.lane || "").toLowerCase() === "landlord";
  const salutation = buildSalutation(
    [opp.decision_maker, opp.contact_name],
    { verb: "Hi", generic: "there" },
  );
  const subject = isLandlord
    ? `Turnover check-in · ${opp.project_address || opp.name || "your properties"}`
    : `Following up · ${opp.project_type || opp.name || "your project"}`;
  const landlordDefault =
    "Checking in — anything need attention between tenants? Send me a photo and I'll tell you what it'll cost and when I can be there.";
  const projectDefault =
    "Just checking in to see if now is a better time to chat.";
  const rec = opp.current_recommendation || (isLandlord ? landlordDefault : projectDefault);
  const cleanRec = stripLeadingGreeting(rec);
  const bodyLines = [
    salutation,
    "",
    cleanRec,
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
    <DaysOnTable
      days={opp.days_on_table}
      testId={`days-on-table-${opp.id}`}
    />
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
            className="inline-flex items-center gap-1.5 h-11 px-4 rounded-md text-[13px] font-semibold"
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
            className="inline-flex items-center gap-1.5 h-11 px-4 rounded-md text-[13px] font-semibold border bh-hairline text-[var(--bh-ink)] hover:bg-[var(--bh-surface-2)]"
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
 * buildReferralDraft — 5-days-after-Won referral ask. Native mailto only,
 * uses the shared salutation helper (never fakes a first name from a
 * business record), never invents details about the finished job — the
 * body is deliberately generic so it works whether the "Won" record has
 * project_type or not.
 */
const buildReferralDraft = (opp, sender) => {
  const senderName = sender?.sender_name || "Ryan";
  const senderPhone = sender?.sender_phone || "";
  const salutation = buildSalutation(
    [opp.decision_maker, opp.contact_name],
    { verb: "Hi", generic: "there" },
  );
  const projectRef = opp.project_type ? ` ${opp.project_type.toLowerCase()}` : "";
  const body = [
    salutation,
    "",
    `Thanks again for having me out for the${projectRef} work — really appreciate the trust you put in me.`,
    "",
    "Quick ask: if there's anyone in your circle who might need similar work, would you mind passing along my info? I'll take good care of them the same way I took care of you.",
    "",
    "Either way, glad I got to work on this one.",
    "",
    `— ${senderName}`,
    senderPhone,
  ]
    .filter((line) => line !== undefined && line !== null)
    .join("\n");
  return {
    subject: `Thanks again — and a quick favor`,
    body,
  };
};

/**
 * ReferralRow — surfaces a Won lead once ≥ 5 days have passed since it
 * closed. One-tap opens the native referral mailto. Never writes back
 * to Airtable — this is a private nudge to Ryan only.
 */
const ReferralRow = ({ opp, sender }) => {
  const email = opp.email || opp.email_alt || "";
  const onAsk = () => {
    if (!email) return;
    const { subject, body } = buildReferralDraft(opp, sender);
    const mailto = `mailto:${encodeURIComponent(email)}?subject=${encodeURIComponent(
      subject,
    )}&body=${encodeURIComponent(body)}`;
    window.location.href = mailto;
  };
  return (
    <div
      data-testid={`referral-row-${opp.id}`}
      className="bh-surface rounded-md p-4"
    >
      <div className="flex items-start justify-between gap-4">
        <Link
          to={`/opportunities/${opp.id}`}
          className="flex-1 min-w-0 hover:opacity-90"
        >
          <div className="font-display text-[16px] text-[var(--bh-ink)] tracking-tight truncate">
            {opp.name || "Unnamed record"}
          </div>
          <div className="mt-1 flex items-center gap-3 text-[12px] text-[var(--bh-ink-mute)] flex-wrap">
            <span
              data-testid={`referral-days-${opp.id}`}
              className="inline-flex items-center gap-1 rounded-full px-2 py-[1px] text-[10px] font-medium tabular-nums whitespace-nowrap"
              style={{ color: "#8a6a3f", background: "rgba(191,150,90,0.14)" }}
              title="Days since this deal closed as Won"
            >
              {opp.days_since_won}d since Won
            </span>
            {opp.decision_maker && (
              <span className="truncate">· {opp.decision_maker}</span>
            )}
            {opp.project_type && <span>· {opp.project_type}</span>}
          </div>
        </Link>
      </div>
      <div className="mt-3 pt-3 border-t bh-hairline flex items-center gap-2">
        {email ? (
          <button
            type="button"
            onClick={onAsk}
            data-testid={`ask-referral-${opp.id}`}
            className="inline-flex items-center gap-1.5 h-11 px-4 rounded-md text-[13px] font-semibold"
            style={{ background: "var(--bh-brass)", color: "var(--bh-surface)" }}
          >
            <Gift size={13} strokeWidth={2} /> Ask for a referral
          </button>
        ) : (
          <span className="text-[11.5px] text-[var(--bh-ink-3)]">
            No email on file — open the record and send by text.
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

/**
 * ENRICHMENT_STALE_DAYS — a Needs Enrichment record older than this
 * gets a "Nudge Claude" one-tap button so it doesn't rot on the table
 * forever. Ryan pastes the resulting prompt into his ongoing Claude
 * conversation (Airtable/Make automation build) or shares it via the
 * iOS share sheet.
 */
const ENRICHMENT_STALE_DAYS = 30;

/**
 * buildClaudeNudgePrompt — compact, ready-to-paste message for Ryan's
 * Claude thread. Includes only governed fields already read by the app —
 * never invents data. Trimmed for iOS share sheet friendliness.
 */
const buildClaudeNudgePrompt = (opp) => {
  const lines = [
    "Please enrich this Bloodhound lead — it has been on the table with no score and no reachable channel:",
    "",
    `• Name: ${opp.name || "Unnamed record"}`,
  ];
  if (opp.project_address) lines.push(`• Address: ${opp.project_address}`);
  if (opp.project_type) lines.push(`• Type: ${opp.project_type}`);
  if (opp.source) lines.push(`• Source: ${opp.source}`);
  if (opp.source_url) lines.push(`• Source URL: ${opp.source_url}`);
  if (typeof opp.days_on_table === "number")
    lines.push(`• On table for: ${opp.days_on_table} days`);
  if (opp.opportunity_id) lines.push(`• Airtable ID: ${opp.opportunity_id}`);
  lines.push("");
  lines.push(
    "Please pull decision maker + verified public business contact (email or phone) and set the governed score, or tag Contact Readiness as Not Reachable so it can be archived.",
  );
  return lines.join("\n");
};

/**
 * EnrichmentRow — Needs Enrichment section. No score AND no reachable
 * channel yet, OR classifier explicitly tagged for enrichment. Read-only
 * (never surfaces messaging controls). Records ≥ ENRICHMENT_STALE_DAYS
 * days old get a "Nudge Claude" button — one tap builds a compact
 * prompt and hands it to the iOS share sheet (native PWA) or clipboard
 * (desktop). Ryan pastes into his Claude thread.
 */
const EnrichmentRow = ({ opp }) => {
  const navigate = useNavigate();
  const stale =
    typeof opp.days_on_table === "number" && opp.days_on_table >= ENRICHMENT_STALE_DAYS;

  const onNudge = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    const prompt = buildClaudeNudgePrompt(opp);
    const title = `Nudge Claude · ${opp.name || "Bloodhound lead"}`;
    // Prefer the native share sheet on iOS PWA — Ryan can pick Claude,
    // Messages, Notes, etc. Fall back to clipboard everywhere else.
    if (typeof navigator !== "undefined" && typeof navigator.share === "function") {
      try {
        await navigator.share({ title, text: prompt });
        return;
      } catch (err) {
        // User cancelled the share sheet — silent no-op.
        if (err && err.name === "AbortError") return;
      }
    }
    try {
      await navigator.clipboard.writeText(prompt);
      toast.success("Prompt copied — paste into your Claude thread.");
    } catch {
      toast.error("Couldn't copy. Open the record and copy manually.");
    }
  };

  const onOpen = () => navigate(`/opportunities/${opp.id}`);

  return (
    <div
      data-testid={`enrichment-row-${opp.id}`}
      onClick={onOpen}
      className="bh-surface rounded-md p-3 transition-colors duration-150 hover:bg-white/[0.03] cursor-pointer"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="font-display text-[15px] text-[var(--bh-ink)] tracking-tight truncate">
            {opp.name || "Unnamed record"}
          </div>
          <div className="mt-1 flex items-center gap-3 text-[12px] text-[var(--bh-ink-mute)] flex-wrap">
            <DaysOnTable
              days={opp.days_on_table}
              testId={`enrichment-days-${opp.id}`}
            />
            {stale && (
              <span
                data-testid={`enrichment-stale-${opp.id}`}
                className="inline-flex items-center gap-1 rounded-full px-2 py-[1px] text-[10px] font-medium tabular-nums whitespace-nowrap"
                style={{ color: "#8a5a45", background: "rgba(138,90,69,0.10)" }}
              >
                Stale
              </span>
            )}
            {opp.project_address && (
              <span className="inline-flex items-center gap-1.5">
                <MapPin size={11} strokeWidth={1.75} />
                {opp.project_address}
              </span>
            )}
            {opp.source && <span>· {sourceLabel(opp.source)}</span>}
          </div>
        </div>
        <ChevronRight
          size={14}
          className="mt-1 shrink-0 text-[var(--bh-ink-3)]"
          strokeWidth={1.75}
        />
      </div>
      {stale && (
        <div className="mt-3 pt-3 border-t bh-hairline flex items-center gap-2">
          <button
            type="button"
            onClick={onNudge}
            data-testid={`nudge-claude-${opp.id}`}
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md text-[12px] font-semibold border bh-hairline text-amber-300 hover:text-amber-200 hover:bg-white/[0.04]"
          >
            <Zap size={12} strokeWidth={2} /> Nudge Claude to enrich
          </button>
          <span className="text-[11px] text-[var(--bh-ink-3)]">
            {opp.days_on_table} days on the table
          </span>
        </div>
      )}
    </div>
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

  const { ready, contacted, referrals, all, enrichment } = useMemo(() => {
    if (!Array.isArray(items))
      return { ready: null, contacted: null, referrals: null, all: null, enrichment: null };
    const readyList = [];
    const contactedList = [];
    const referralList = [];
    const allList = [];
    const enrichmentList = [];
    for (const opp of items) {
      // Won leads with the 5-day referral window elapsed get their own
      // top-of-mind lane — never mixed into Ready/Contacted/All.
      if (opp.status === "Won" && opp.referral_prompt_ready) {
        referralList.push(opp);
        continue;
      }
      const bucket = queueBucket(opp);
      if (bucket === "ready") readyList.push(opp);
      else if (bucket === "contacted") contactedList.push(opp);
      else if (needsEnrichment(opp)) enrichmentList.push(opp);
      else allList.push(opp);
    }
    return {
      ready: sortForQueue(readyList),
      contacted: sortForQueue(contactedList),
      // Freshest referrals first (recently-Won leads are easier for the
      // customer to remember). Ties broken by longer wait.
      referrals: [...referralList].sort(
        (a, b) => (a.days_since_won ?? 0) - (b.days_since_won ?? 0),
      ),
      all: sortForQueue(allList),
      // Enrichment records have no governed score by definition — sort by
      // days-on-table so the oldest (most in need of a nudge to the
      // enrichment pipeline) surface first.
      enrichment: [...enrichmentList].sort(
        (a, b) => (b.days_on_table ?? 0) - (a.days_on_table ?? 0),
      ),
    };
  }, [items]);

  const [enrichmentOpen, setEnrichmentOpen] = useState(false);

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

        {referrals && referrals.length > 0 && (
          <SectionShell
            testId="section-referrals-due"
            eyebrow="3 · Referrals due"
            title="Ask for a referral"
            hint="Leads that closed as Won at least 5 days ago. Customer memory is still fresh — one tap opens a native referral ask. Nothing writes back to Airtable."
            icon={Gift}
            count={referrals.length}
          >
            <div className="space-y-2">
              {referrals.map((opp) => (
                <ReferralRow key={opp.id} opp={opp} sender={senderSettings} />
              ))}
            </div>
          </SectionShell>
        )}

        <SectionShell
          testId="section-all-projects"
          eyebrow={referrals && referrals.length > 0 ? "4 · All Projects" : "3 · All Projects"}
          title="All Projects"
          hint="Everything else — paused, needs proof, needs history check, or not appropriate. These records have been enriched but aren't ready yet. Read-only view. No outreach actions."
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

        <section data-testid="section-needs-enrichment" className="space-y-3">
          <button
            type="button"
            data-testid="needs-enrichment-toggle"
            onClick={() => setEnrichmentOpen((v) => !v)}
            className="w-full text-left flex items-start gap-3 py-1 hover:opacity-90 transition-opacity"
          >
            <div className="flex-1">
              <div className="mono text-[10px] uppercase tracking-widest text-neutral-500 flex items-center gap-1.5">
                <Snowflake size={11} strokeWidth={1.75} />
                4 · Cold — Needs Enrichment
              </div>
              <h2 className="font-display text-[22px] text-[var(--bh-ink)] tracking-tight">
                Needs Enrichment
                {enrichment?.length ? (
                  <span
                    className="ml-2 text-[13px] text-[var(--bh-ink-mute)] tabular-nums"
                    data-testid="needs-enrichment-count"
                  >
                    ({enrichment.length})
                  </span>
                ) : null}
              </h2>
              <p className="text-[12.5px] text-[var(--bh-ink-mute)] mt-0.5 max-w-2xl leading-relaxed">
                Records the classifier tagged as needing enrichment, or that
                still have no score and no reachable channel. Kept on
                production so the enrichment pipeline keeps working on them —
                never surfaced in the day's work list. Tap to {enrichmentOpen ? "collapse" : "expand"}.
              </p>
            </div>
            <ChevronDown
              size={16}
              strokeWidth={1.75}
              className={
                "mt-2 shrink-0 text-[var(--bh-ink-3)] transition-transform duration-150 " +
                (enrichmentOpen ? "rotate-180" : "")
              }
            />
          </button>

          {enrichmentOpen && (
            <div data-testid="needs-enrichment-list">
              {enrichment === null ? (
                <EmptyCard testId="enrichment-loading">Loading…</EmptyCard>
              ) : enrichment.length === 0 ? (
                <EmptyCard testId="enrichment-empty">
                  Nothing needs enrichment right now — every unclassified
                  record either has a governed score or a reachable channel.
                </EmptyCard>
              ) : (
                <div className="space-y-1.5">
                  {enrichment.slice(0, 60).map((opp) => (
                    <EnrichmentRow key={opp.id} opp={opp} />
                  ))}
                  {enrichment.length > 60 && (
                    <div className="pt-2 text-[12px] text-[var(--bh-ink-3)]">
                      Showing 60 of {enrichment.length}.
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </section>
      </main>
    </>
  );
};

export default CommandCenter;
