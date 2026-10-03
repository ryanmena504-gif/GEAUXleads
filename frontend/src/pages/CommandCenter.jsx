import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import TopHeader from "@/components/TopHeader";
import LearningStrip from "@/components/LearningStrip";
import FreshIntel from "@/components/FreshIntel";
import Bench from "@/components/Bench";
import OpenInMessages from "@/components/OpenInMessages";
import { api } from "@/lib/api";
import { useLiveUpdates } from "@/hooks/useLiveUpdates";
import { moneyDisplay, sourceLabel } from "@/lib/formatters";
import {
  queueBucket,
  sortForQueue,
  notReadyReason,
  needsEnrichment,
  nextTouch,
  outreachAllowed,
} from "@/lib/queue";
import useUserSettings from "@/hooks/useUserSettings";
import DaysOnTable from "@/components/DaysOnTable";
import { buildSalutation } from "@/lib/greeting";
import {
  Check,
  ChevronRight,
  ChevronDown,
  ExternalLink,
  Gift,
  Loader2,
  MapPin,
  Zap,
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
    "Please enrich this GEAUXleads lead — it has been on the table with no score and no reachable channel:",
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
    const title = `Nudge Claude · ${opp.name || "GEAUXleads lead"}`;
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

// ─── Today: work tickets ──────────────────────────────────────────────────
//
// Home reads like the day's job sheet: one ticket on top for the next person
// to reach, the rest as stubs underneath. Every message button is
// OpenInMessages, so the global outreachAllowed() gate, the 4-touch limit and
// the draft-safety check all apply here exactly as on the detail page.

const todayUtc = () => new Date().toISOString().slice(0, 10);

const sentToday = (opp) => {
  const d = (opp.message_sent_date || opp.date_contacted || "").slice(0, 10);
  return Boolean(d) && d >= todayUtc();
};

const ticketNo = (n) => `No. ${String(n).padStart(2, "0")}`;

const MarkSentButton = ({ opp, busy, onSent }) => (
  <button
    type="button"
    disabled={busy}
    onClick={() => onSent(opp.id)}
    data-testid={`mark-sent-${opp.id}`}
    title="Tap after you've sent it from your mail app"
    className="inline-flex items-center gap-1.5 h-9 px-3 rounded-md text-[12px] font-medium border bh-hairline text-[var(--bh-olive)] hover:bg-[var(--bh-olive-mute)] transition-colors disabled:opacity-60"
  >
    {busy ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} I sent it
  </button>
);

const TicketHero = ({ opp, n, busy, onSent }) => {
  const money = moneyDisplay(opp);
  const meta = [opp.project_address, opp.project_type, opp.source && `via ${sourceLabel(opp.source)}`]
    .filter(Boolean)
    .join(" · ");
  return (
    <article data-testid={`ticket-hero-${opp.id}`} className="bh-ticket bh-ticket--hero">
      <div className="px-5 pt-4 pb-4">
        <div className="flex items-center justify-between gap-3">
          <span className="mono text-[10.5px] uppercase tracking-[0.18em] text-[var(--bh-brass)]">
            {ticketNo(n)} · Up next
          </span>
          {money && (
            <span className="text-right">
              <span className="font-display text-[20px] tabular-nums text-[var(--bh-ink)]">{money}</span>
              <span className="block text-[10.5px] text-[var(--bh-ink-mute)]">possible work</span>
            </span>
          )}
        </div>
        <Link to={`/opportunities/${opp.id}`} className="block mt-1 group">
          <h3 className="font-display text-[26px] leading-tight tracking-tight text-[var(--bh-ink)] group-hover:underline decoration-[var(--bh-hair-warm)] underline-offset-4">
            {opp.name}
          </h3>
          {meta && <div className="mt-1 text-[12.5px] text-[var(--bh-ink-mute)]">{meta}</div>}
        </Link>
      </div>
      <div className="bh-perforation" aria-hidden="true" />
      <dl className="px-5 py-4 space-y-2.5 text-[14px] leading-relaxed">
        {opp.priority_explanation && (
          <div className="grid grid-cols-[72px_1fr] gap-3">
            <dt className="mono text-[10px] uppercase tracking-widest text-[var(--bh-ink-mute)] pt-1">Why now</dt>
            <dd className="text-[var(--bh-ink-2)]">{opp.priority_explanation}</dd>
          </div>
        )}
        {opp.current_recommendation && (
          <div className="grid grid-cols-[72px_1fr] gap-3">
            <dt className="mono text-[10px] uppercase tracking-widest text-[var(--bh-ink-mute)] pt-1">Do this</dt>
            <dd className="text-[var(--bh-ink)]">{opp.current_recommendation}</dd>
          </div>
        )}
      </dl>
      <div className="px-5 pb-5 flex flex-wrap items-center gap-2">
        <OpenInMessages opportunity={opp} variant="pill" />
        <MarkSentButton opp={opp} busy={busy} onSent={onSent} />
        <SourceChip opp={opp} />
        <Link
          to={`/opportunities/${opp.id}`}
          className="ml-auto text-[12px] text-[var(--bh-ink-3)] hover:text-[var(--bh-ink)] inline-flex items-center gap-1"
        >
          Open <ChevronRight size={12} />
        </Link>
      </div>
    </article>
  );
};

const TicketStub = ({ opp, n, busy, onSent }) => {
  const money = moneyDisplay(opp);
  const why = opp.priority_explanation || opp.current_recommendation;
  return (
    <article data-testid={`ticket-stub-${opp.id}`} className="bh-ticket flex items-stretch">
      <div className="w-14 shrink-0 flex items-start justify-center pt-3.5 border-r border-dashed bh-hairline-strong">
        <span className="mono text-[11px] tabular-nums text-[var(--bh-ink-mute)]">
          {String(n).padStart(2, "0")}
        </span>
      </div>
      <div className="flex-1 min-w-0 p-3 sm:flex sm:items-center sm:gap-4">
        <Link to={`/opportunities/${opp.id}`} className="flex-1 min-w-0 block group">
          <div className="flex items-baseline gap-2">
            <span className="text-[15px] font-semibold text-[var(--bh-ink)] truncate group-hover:underline">
              {opp.name}
            </span>
            {money && (
              <span className="shrink-0 text-[12px] tabular-nums text-[var(--bh-ink-3)]">{money}</span>
            )}
          </div>
          {why && <div className="mt-0.5 text-[12.5px] text-[var(--bh-ink-3)] line-clamp-1">{why}</div>}
        </Link>
        <div className="mt-2 sm:mt-0 flex items-center gap-2 shrink-0">
          <OpenInMessages opportunity={opp} variant="pill" />
          <MarkSentButton opp={opp} busy={busy} onSent={onSent} />
        </div>
      </div>
    </article>
  );
};

/**
 * WaitingRow — someone Ryan already reached. Shows which touch is next and
 * when; the follow-up control is OpenInMessages (follow-up mode only).
 */
const WaitingRow = ({ opp }) => {
  const next = nextTouch(opp);
  const lastBit = opp.reply_summary || opp.current_recommendation;
  return (
    <article data-testid={`waiting-row-${opp.id}`} className="bh-surface rounded-md p-3.5">
      <div className="flex items-start gap-3">
        <Link to={`/opportunities/${opp.id}`} className="flex-1 min-w-0 group">
          <div className="text-[15px] font-semibold text-[var(--bh-ink)] truncate group-hover:underline">
            {opp.name}
          </div>
          <div className="mt-0.5 text-[12px] text-[var(--bh-ink-mute)] flex flex-wrap gap-x-2">
            {opp.contact_state && <span>{opp.contact_state}</span>}
            {next && <span>· Next: touch {next.attempt} of 4, {next.label.toLowerCase()}</span>}
            {opp.next_follow_up && <span>· due {opp.next_follow_up}</span>}
          </div>
          {lastBit && <div className="mt-1 text-[12.5px] text-[var(--bh-ink-3)] line-clamp-2">{lastBit}</div>}
        </Link>
      </div>
      <div className="mt-2.5">
        <OpenInMessages opportunity={opp} variant="pill" />
      </div>
    </article>
  );
};

const Disclosure = ({ testId, title, count, hint, open, onToggle, children }) => (
  <section data-testid={testId} className="border-t bh-hairline pt-4">
    <button
      type="button"
      data-testid={`${testId}-toggle`}
      onClick={onToggle}
      className="w-full flex items-center gap-3 text-left"
    >
      <span className="flex-1">
        <span className="text-[15px] font-semibold text-[var(--bh-ink)]">{title}</span>
        {typeof count === "number" && (
          <span className="ml-2 text-[13px] tabular-nums text-[var(--bh-ink-mute)]">{count}</span>
        )}
        {hint && <span className="block text-[12px] text-[var(--bh-ink-mute)] mt-0.5">{hint}</span>}
      </span>
      <ChevronDown
        size={16}
        strokeWidth={1.75}
        className={"shrink-0 text-[var(--bh-ink-3)] transition-transform " + (open ? "rotate-180" : "")}
      />
    </button>
    {open && <div className="mt-3 space-y-1.5">{children}</div>}
  </section>
);

const Chapter = ({ title, aside, children, testId }) => (
  <section data-testid={testId} className="space-y-3">
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 border-b bh-hairline pb-2">
      <h2 className="font-display text-[21px] tracking-tight text-[var(--bh-ink)] whitespace-nowrap">{title}</h2>
      {aside && <span className="text-[12px] text-[var(--bh-ink-mute)]">{aside}</span>}
    </div>
    {children}
  </section>
);

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

const DayHeadline = ({ ready, due, referrals, progress }) => {
  const dateLabel = new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
  let headline;
  if (ready === null) headline = "Pulling today's list…";
  else if (ready > 0) headline = `${plural(ready, "person is", "people are")} ready to hear from you.`;
  else if (due > 0) headline = "No new introductions today — just follow-ups.";
  else headline = "Nobody's waiting on you. Go build relationships.";
  const extras = [
    due > 0 && plural(due, "follow-up is due", "follow-ups are due"),
    referrals > 0 && `${plural(referrals, "happy customer", "happy customers")} to ask for a referral`,
  ].filter(Boolean);
  const pct = progress && progress.target > 0 ? Math.min(100, (progress.sent_today / progress.target) * 100) : 0;
  return (
    <header data-testid="day-headline" className="pt-1">
      <div className="mono text-[10.5px] uppercase tracking-[0.18em] text-[var(--bh-ink-mute)]">{dateLabel}</div>
      <h1 className="mt-2 font-display text-[30px] sm:text-[36px] leading-[1.1] tracking-tight text-[var(--bh-ink)] max-w-2xl">
        {headline}
      </h1>
      {extras.length > 0 && (
        <p className="mt-2 text-[14px] text-[var(--bh-ink-3)]">{extras.join(" · ")}.</p>
      )}
      {progress && progress.target > 0 && (
        <div className="mt-4 flex items-center gap-3 max-w-md" data-testid="outreach-progress">
          <div className="flex-1 h-1.5 rounded-full overflow-hidden bg-[var(--bh-surface-2)]">
            <div className="h-full rounded-full transition-all duration-300" style={{ width: `${pct}%`, background: "var(--bh-brass)" }} />
          </div>
          <span className="text-[12px] tabular-nums text-[var(--bh-ink-3)] whitespace-nowrap">
            {progress.sent_today} of {progress.target} touches today
          </span>
        </div>
      )}
    </header>
  );
};

// ─── Page ─────────────────────────────────────────────────────────────────

const CommandCenter = () => {
  const [items, setItems] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [progress, setProgress] = useState(null);
  const [markingId, setMarkingId] = useState(null);
  const [open, setOpen] = useState({ more: false, parked: false, enrichment: false });
  const { settings: senderSettings } = useUserSettings();

  const load = useCallback(() => {
    api
      .listOpportunities()
      .then((rows) => {
        setItems(rows);
        setLoadError(null);
      })
      .catch(() => {
        // Keep the last good list on a failed live refresh; only show an
        // error instead of silently rendering empty queues.
        setItems((prev) => prev ?? []);
        setLoadError("Could not load your projects — the GEAUXleads API didn't respond.");
      });
    api
      .outreachQueue()
      .then((res) => setProgress({ target: res.target, sent_today: res.sent_today }))
      .catch(() => setProgress(null));
  }, []);

  useEffect(() => {
    load();
  }, [load]);
  useLiveUpdates(load);

  const markSent = useCallback(
    async (id) => {
      setMarkingId(id);
      try {
        await api.recordResult(id, { event: "sent", channel: "Email" });
        toast.success("Logged. On to the next one.");
        load();
      } catch (err) {
        toast.error(err?.response?.data?.detail || err?.message || "Couldn't log it as sent");
      } finally {
        setMarkingId(null);
      }
    },
    [load],
  );

  const lists = useMemo(() => {
    if (!Array.isArray(items)) return null;
    const ready = [];
    const contacted = [];
    const referrals = [];
    const parked = [];
    const enrichment = [];
    for (const opp of items) {
      // Won leads with the 5-day referral window elapsed get their own lane.
      if (opp.status === "Won" && opp.referral_prompt_ready) {
        referrals.push(opp);
        continue;
      }
      const bucket = queueBucket(opp);
      if (bucket === "ready") {
        if (!sentToday(opp)) ready.push(opp);
      } else if (bucket === "contacted") contacted.push(opp);
      else if (needsEnrichment(opp)) enrichment.push(opp);
      else parked.push(opp);
    }
    // Follow-ups that still have a touch left, soonest due first.
    const waiting = sortForQueue(contacted.filter((o) => outreachAllowed(o) === "follow_up"));
    waiting.sort((a, b) => String(a.next_follow_up || "9999").localeCompare(String(b.next_follow_up || "9999")));
    return {
      ready: sortForQueue(ready),
      waiting,
      referrals: referrals.sort((a, b) => (a.days_since_won ?? 0) - (b.days_since_won ?? 0)),
      parked: sortForQueue(parked),
      enrichment: enrichment.sort((a, b) => (b.days_on_table ?? 0) - (a.days_on_table ?? 0)),
    };
  }, [items]);

  const target = progress?.target || 10;
  const todayStack = lists ? lists.ready.slice(0, target) : [];
  const beyond = lists ? lists.ready.slice(target) : [];
  const [hero, ...stubs] = todayStack;
  const toggle = (k) => setOpen((o) => ({ ...o, [k]: !o[k] }));

  return (
    <>
      <TopHeader pageTitle="Today" subtitle="Who to reach, in order" />
      <main className="px-4 lg:px-8 py-6 pb-28 max-w-4xl space-y-10">
        {loadError && (
          <div
            role="alert"
            data-testid="home-load-error"
            className="bh-surface rounded-md border-t-2 border-t-red-500/60 p-4 text-sm text-red-200"
          >
            {loadError} The lists below may be empty or out of date — reload to try again.
          </div>
        )}

        <DayHeadline
          ready={lists ? lists.ready.length : null}
          due={lists ? lists.waiting.length : 0}
          referrals={lists ? lists.referrals.length : 0}
          progress={progress}
        />

        {lists === null ? (
          <EmptyCard testId="today-loading">Loading…</EmptyCard>
        ) : (
          <Chapter
            testId="section-ready-to-contact"
            title="Reach out"
            aside={lists.ready.length ? "Best fit first" : null}
          >
            {hero ? (
              <div className="space-y-2">
                <TicketHero opp={hero} n={1} busy={markingId === hero.id} onSent={markSent} />
                {stubs.map((opp, i) => (
                  <TicketStub key={opp.id} opp={opp} n={i + 2} busy={markingId === opp.id} onSent={markSent} />
                ))}
              </div>
            ) : (
              <EmptyCard testId="ready-empty">
                Nobody new is cleared for first contact right now. Your bench below is where the next ones come from.
              </EmptyCard>
            )}
            {beyond.length > 0 && (
              <Disclosure
                testId="ready-beyond-target"
                title="Also ready"
                count={beyond.length}
                hint={`Past today's target of ${target}.`}
                open={open.more}
                onToggle={() => toggle("more")}
              >
                {beyond.map((opp, i) => (
                  <TicketStub key={opp.id} opp={opp} n={target + i + 1} busy={markingId === opp.id} onSent={markSent} />
                ))}
              </Disclosure>
            )}
          </Chapter>
        )}

        {lists && lists.waiting.length > 0 && (
          <Chapter testId="section-contacted" title="Waiting on them" aside="Soonest due first">
            <div className="space-y-2">
              {lists.waiting.map((opp) => (
                <WaitingRow key={opp.id} opp={opp} />
              ))}
            </div>
          </Chapter>
        )}

        {lists && lists.referrals.length > 0 && (
          <Chapter testId="section-referrals-due" title="Ask for a referral" aside="Won 5+ days ago">
            <div className="space-y-2">
              {lists.referrals.map((opp) => (
                <ReferralRow key={opp.id} opp={opp} sender={senderSettings} />
              ))}
            </div>
          </Chapter>
        )}

        <Chapter
          testId="section-bench"
          title="Your bench"
          aside="Repeat work comes from people, not permits"
        >
          <Bench />
        </Chapter>

        <FreshIntel />
        <LearningStrip />

        {lists && (
          <div className="space-y-4">
            <Disclosure
              testId="section-all-projects"
              title="Parked"
              count={lists.parked.length}
              hint="Enriched but not ready — needs proof, paused, or not a fit. No outreach from here."
              open={open.parked}
              onToggle={() => toggle("parked")}
            >
              {lists.parked.slice(0, 40).map((opp) => (
                <AllProjectsRow key={opp.id} opp={opp} />
              ))}
              {lists.parked.length > 40 && (
                <Link to="/opportunities" className="block pt-2 text-[12px] text-[var(--bh-ink-3)] hover:text-[var(--bh-ink)]">
                  Showing 40 of {lists.parked.length} — see them all in Opportunities
                </Link>
              )}
            </Disclosure>
            <Disclosure
              testId="section-needs-enrichment"
              title="Needs research"
              count={lists.enrichment.length}
              hint="No score and no way to reach them yet. The enrichment pipeline keeps working on these."
              open={open.enrichment}
              onToggle={() => toggle("enrichment")}
            >
              {lists.enrichment.slice(0, 60).map((opp) => (
                <EnrichmentRow key={opp.id} opp={opp} />
              ))}
            </Disclosure>
          </div>
        )}
      </main>
    </>
  );
};

export default CommandCenter;
