import React from "react";
import { Mail, Reply, ShieldCheck } from "lucide-react";
import { useUserSettings } from "@/hooks/useUserSettings";
import { outreachAllowed } from "@/lib/queue";

/**
 * OpenInMessages — the single Email Now / Follow Up Email button.
 *
 *   • Current Queue = "Ready to Contact" → one primary button "Email Now"
 *     that opens the device-native email app via a plain mailto:. The mailto
 *     includes the verified public business email, the playbook subject, and
 *     the personalized playbook body.
 *   • Current Queue = "Contacted"        → one primary button "Follow Up
 *     Email" that opens the device-native email app with a preloaded
 *     follow-up message.
 *   • Current Queue = "All Projects"     → NOTHING is rendered.
 *
 * If there is no verified public business email on file, NOTHING is rendered.
 * SMS is never substituted merely because a phone number exists.
 *
 * Clicking either button writes nothing to the backend. There is no
 * intermediate modal, drawer, template picker, copy button, or preview —
 * one tap → mailto → Ryan presses Send in his own email app.
 */

// Default sender identity — used only for the plain-text signature that
// appears in the mailto body. Never for provider APIs or automated sends.
const DEFAULT_SENDER_EMAIL = "ryanmena@theshirtlesshandyman.com";
const DEFAULT_SENDER_NAME = "Ryan Mena";
const DEFAULT_SENDER_PHONE = "(504) 264-4919";

const enc = encodeURIComponent;

const withSignature = (body, senderName, senderPhone) => {
  const base = (body || "").trim();
  const name = (senderName || DEFAULT_SENDER_NAME).trim();
  const phone = (senderPhone || DEFAULT_SENDER_PHONE).trim();
  const lines = [name, "The Shirtless Handyman"];
  if (phone) lines.push(phone);
  const signature = `\n\n${lines.join("\n")}`;
  return base ? `${base}${signature}` : signature.trimStart();
};

const buildFirstDraft = (opp, sender) => {
  const first = (opp?.decision_maker || opp?.name || "there").split(" ")[0];
  const subject =
    opp?.first_message_subject ||
    `Quick note about ${opp?.project_type || "your project"}`;
  const body = [
    `Hi ${first},`,
    "",
    opp?.first_message ||
      opp?.first_contact_message ||
      "I came across your recent project and thought I could help.",
  ]
    .filter(Boolean)
    .join("\n");
  return {
    subject,
    body: withSignature(body, sender?.sender_name, sender?.sender_phone),
  };
};

const buildFollowUpDraft = (opp, sender) => {
  const first = (opp?.decision_maker || opp?.name || "there").split(" ")[0];
  const subject = `Following up · ${opp?.project_type || opp?.name || "your project"}`;
  const body = [
    `Hi ${first},`,
    "",
    opp?.current_recommendation ||
      "Just checking in to see if now is a better time to chat.",
  ]
    .filter(Boolean)
    .join("\n");
  return {
    subject,
    body: withSignature(body, sender?.sender_name, sender?.sender_phone),
  };
};

const pickEmail = (opp) => {
  const raw = (opp?.email || opp?.email_alt || opp?.contact_email || "").toString().trim();
  return raw && raw.includes("@") ? raw : null;
};

const btnBase =
  "inline-flex items-center justify-center gap-1.5 rounded-md font-semibold " +
  "transition-colors duration-150 whitespace-nowrap no-underline";
const SIZE = {
  md: "h-11 px-4 text-sm",
  sm: "h-9 px-3 text-[12.5px]",
};
const primary = { background: "var(--bh-brass)", color: "var(--bh-surface)" };
const secondary = {
  background: "var(--bh-surface)",
  border: "1px solid var(--bh-hair-strong)",
  color: "var(--bh-ink)",
};

/**
 * @param {object} props
 * @param {object} props.opportunity — full opportunity DTO
 * @param {"pill"|"panel"} [props.variant]
 */
export const OpenInMessages = ({ opportunity, variant = "panel" }) => {
  const { settings } = useUserSettings();
  const senderIdentity = {
    sender_name: settings?.sender_name,
    sender_phone: settings?.sender_phone,
  };

  const mode = outreachAllowed(opportunity);
  const email = pickEmail(opportunity);

  // GLOBAL GATES:
  //   • All Projects (or unclassified) → render nothing.
  //   • No verified public business email → render nothing (never substitute
  //     SMS because a phone number exists).
  if (mode === "none" || !email) return null;

  const isFollowup = mode === "follow_up";
  const draft = isFollowup
    ? buildFollowUpDraft(opportunity, senderIdentity)
    : buildFirstDraft(opportunity, senderIdentity);
  const href = `mailto:${enc(email)}?subject=${enc(draft.subject)}&body=${enc(draft.body)}`;
  const testid = isFollowup
    ? `follow-up-email-${opportunity?.id || "unknown"}`
    : `email-now-${opportunity?.id || "unknown"}`;
  const label = isFollowup ? "Follow Up Email" : "Email Now";
  const Icon = isFollowup ? Reply : Mail;
  const styleOverride = variant === "pill" ? (isFollowup ? secondary : primary) : primary;
  const size = variant === "pill" ? "sm" : "md";

  const buttonNode = (
    <a
      href={href}
      data-testid={testid}
      className={`${btnBase} ${SIZE[size]}`}
      style={styleOverride}
    >
      <Icon size={size === "sm" ? 13 : 14} /> {label}
    </a>
  );

  if (variant === "pill") {
    return (
      <div className="flex items-center gap-1.5" data-testid="lead-email-pill">
        {buttonNode}
      </div>
    );
  }

  // Panel — one primary button + a plain-English guarantee line. NO template
  // picker, NO copy button, NO preview screen.
  const contextBadge = isFollowup && opportunity?.contact_state ? (
    <span
      className="text-[10.5px] px-2 py-0.5 rounded-full font-medium tabular-nums"
      style={{
        background: "var(--bh-surface)",
        border: "1px solid var(--bh-hair-warm)",
        color: "var(--bh-brass)",
      }}
      data-testid="followup-contact-state"
    >
      {opportunity.contact_state}
    </span>
  ) : null;

  return (
    <div
      className="rounded-md border p-4 space-y-3"
      style={{ background: "var(--bh-brass-mute)", borderColor: "var(--bh-hair-warm)" }}
      data-testid={isFollowup ? "follow-up-email-panel" : "email-now-panel"}
    >
      <div className="flex items-center gap-2">
        <Icon size={13} style={{ color: "var(--bh-brass)" }} />
        <span className="bh-eyebrow" style={{ color: "var(--bh-brass)" }}>
          {isFollowup ? "Follow up" : "Contact them"}
        </span>
        {contextBadge}
      </div>
      <div>{buttonNode}</div>
      <div className="text-[11.5px] leading-relaxed text-[var(--bh-ink-2)]">
        Opens a draft in your default mail app. Nothing sends until you press
        Send yourself.
      </div>
      <div className="text-[11px] text-[var(--bh-ink-3)] inline-flex items-center gap-1.5">
        <ShieldCheck size={11} style={{ color: "var(--bh-olive)" }} />
        {isFollowup
          ? "Follow-up draft only. First-contact controls stay hidden on Contacted records."
          : "Native mailto handoff. No provider API, no automated send."}
      </div>
    </div>
  );
};

/**
 * resolveContacts — kept as a named export for legacy pages (Intelligence).
 * Under the Email-Now workflow the app only ever returns an email link.
 */
export const resolveContacts = (opp) => {
  const mode = outreachAllowed(opp);
  const email = pickEmail(opp);
  if (mode === "none" || !email) return { text: null, email: null };
  const draft = mode === "follow_up"
    ? buildFollowUpDraft(opp, {})
    : buildFirstDraft(opp, {});
  return {
    text: null,
    email: {
      href: `mailto:${enc(email)}?subject=${enc(draft.subject)}&body=${enc(draft.body)}`,
      display: email,
      external: false,
    },
  };
};

export default OpenInMessages;
