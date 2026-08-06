import React, { useState } from "react";
import { MessageSquare, Mail, Lock, ShieldCheck, ArrowRight } from "lucide-react";

/**
 * OpenInMessages — approval-only lead-contact selector.
 *
 * Three visible choices per lead:
 *   • TEXT  — sms: handoff (Apple Messages)
 *   • EMAIL — mailto: handoff (Apple Mail on iPhone)
 *   • BOTH  — appears only when phone AND email both exist. Opens Messages
 *             first; a follow-up "Open email draft" button appears so the
 *             user can hand off to Mail themselves after returning.
 *
 * ZERO backend writes. Nothing is sent, scheduled, or logged when any of
 * these buttons is tapped. Approval-only policy intact.
 */

const RYAN_EMAIL = "ryanmena@theshirtlesshandyman.com";
const EMAIL_SUBJECT = "Quick question about your project";

// iOS is strict: sms: URLs must contain digits (with optional leading `+`)
// only — no parens, no spaces, no dashes. Otherwise Safari throws
// "Failed to load" and refuses to hand off to Messages.
const sanitizeSmsUrl = (rawUrl) => {
  if (typeof rawUrl !== "string") return null;
  const trimmed = rawUrl.trim();
  if (!/^sms:/i.test(trimmed)) return null;
  const rest = trimmed.slice(4);
  const qIdx = rest.search(/[?&]/);
  const rawPhone = qIdx === -1 ? rest : rest.slice(0, qIdx);
  const query = qIdx === -1 ? "" : rest.slice(qIdx + 1);
  let phone = rawPhone.replace(/[^\d+]/g, "");
  if (phone.startsWith("+")) {
    phone = "+" + phone.slice(1).replace(/\+/g, "");
  } else {
    phone = phone.replace(/\+/g, "");
  }
  if (!phone) return null;
  return query ? `sms:${phone}&${query.replace(/^\?/, "")}` : `sms:${phone}`;
};

const buildIosSmsHref = (phone, body) => {
  if (!phone) return null;
  const cleanPhone = String(phone).replace(/[^\d+]/g, "");
  if (!cleanPhone) return null;
  const q = body ? `&body=${encodeURIComponent(String(body).trim())}` : "";
  return `sms:${cleanPhone}${q}`;
};

// mailto: signature. Includes Ryan's sender email so it's visible in the
// composed draft — iPhone Mail can't be forced to a specific From account
// via mailto, so this at least surfaces the correct address to send from.
const withSignature = (body) => {
  const base = (body || "").trim();
  const signature = `\n\nRyan Mena\nThe Shirtless Handyman\n${RYAN_EMAIL}`;
  if (!base) return signature.trimStart();
  if (base.endsWith(RYAN_EMAIL)) return base;
  return `${base}${signature}`;
};

const buildMailtoHref = (email) => {
  if (!email) return null;
  const clean = String(email).trim();
  if (!clean.includes("@")) return null;
  const params = [
    `subject=${encodeURIComponent(EMAIL_SUBJECT)}`,
  ];
  return `mailto:${clean}?${params.join("&")}`;
};

const buildMailtoWithBody = (email, body) => {
  if (!email) return null;
  const clean = String(email).trim();
  if (!clean.includes("@")) return null;
  const params = [
    `subject=${encodeURIComponent(EMAIL_SUBJECT)}`,
    `body=${encodeURIComponent(withSignature(body))}`,
  ];
  return `mailto:${clean}?${params.join("&")}`;
};

const pickMessage = (opp) =>
  opp?.first_contact_message || opp?.first_message || "";

const cleanDisplayPhone = (p) => {
  if (!p) return null;
  const s = String(p).trim();
  return s || null;
};

export const resolveContacts = (opp) => {
  if (!opp) return { text: null, email: null };
  const iphoneFormula = (opp.open_approved_message_iphone || "").toString().trim();
  const phoneRaw = (opp.contact_phone || opp.phone || opp.phone_number || "").toString().trim();
  const emailRaw = (opp.contact_email || opp.email || "").toString().trim();
  const message = pickMessage(opp);

  let textHref = null;
  let textDisplay = null;
  if (iphoneFormula.toLowerCase().startsWith("sms:")) {
    textHref = sanitizeSmsUrl(iphoneFormula);
    textDisplay = cleanDisplayPhone(phoneRaw) || "iPhone formula";
  } else if (phoneRaw && message) {
    textHref = buildIosSmsHref(phoneRaw, message);
    textDisplay = cleanDisplayPhone(phoneRaw);
  } else if (phoneRaw) {
    // Phone exists but no message body — still allow the handoff.
    textHref = buildIosSmsHref(phoneRaw, "");
    textDisplay = cleanDisplayPhone(phoneRaw);
  }

  let emailHref = null;
  let emailDisplay = null;
  if (emailRaw && emailRaw.includes("@")) {
    emailHref = message
      ? buildMailtoWithBody(emailRaw, message)
      : buildMailtoHref(emailRaw);
    emailDisplay = emailRaw;
  }

  return {
    text: textHref ? { href: textHref, display: textDisplay } : null,
    email: emailHref ? { href: emailHref, display: emailDisplay } : null,
  };
};

const btnBase =
  "inline-flex items-center justify-center gap-1.5 h-11 px-4 rounded-md text-sm font-medium " +
  "transition-colors duration-150 whitespace-nowrap no-underline";

const primary = {
  background: "var(--bh-brass)",
  color: "var(--bh-surface)",
};
const secondary = {
  background: "var(--bh-surface)",
  border: "1px solid var(--bh-hair-strong)",
  color: "var(--bh-ink)",
};
const disabled = {
  background: "var(--bh-surface-2)",
  border: "1px solid var(--bh-hair)",
  color: "var(--bh-ink-mute)",
};

const TextButton = ({ href, testid, label, onClick, styleOverride }) => (
  <a
    href={href}
    data-testid={testid}
    onClick={onClick}
    className={btnBase}
    style={styleOverride || primary}
  >
    <MessageSquare size={14} /> {label}
  </a>
);

const EmailButton = ({ href, testid, label, styleOverride }) => (
  <a
    href={href}
    data-testid={testid}
    className={btnBase}
    style={styleOverride || primary}
  >
    <Mail size={14} /> {label}
  </a>
);

const DisabledButton = () => (
  <button
    type="button"
    disabled
    data-testid="open-in-messages-disabled"
    className={btnBase + " cursor-not-allowed"}
    style={disabled}
  >
    <Lock size={14} /> Public contact needed
  </button>
);

/**
 * @param {object} props
 * @param {object} props.opportunity — full opportunity DTO
 * @param {"pill"|"panel"|"row"} [props.variant]
 */
export const OpenInMessages = ({ opportunity, variant = "panel" }) => {
  const contacts = resolveContacts(opportunity);
  const hasText = !!contacts.text;
  const hasEmail = !!contacts.email;
  const hasBoth = hasText && hasEmail;

  // Once the user taps a TEXT handoff on a BOTH lead, reveal a follow-up
  // "Open email draft" primary button. Do NOT auto-launch Mail — the user
  // presses it themselves after returning from Messages.
  const [textedFirst, setTextedFirst] = useState(false);

  if (!hasText && !hasEmail) {
    return (
      <div
        className="rounded-md border p-4 space-y-2"
        style={{ background: "var(--bh-surface-2)", borderColor: "var(--bh-hair)" }}
        data-testid="open-in-messages-panel"
      >
        <div className="flex items-center gap-2">
          <MessageSquare size={13} style={{ color: "var(--bh-ink-mute)" }} />
          <span className="bh-eyebrow" style={{ color: "var(--bh-ink-mute)" }}>
            iPhone handoff
          </span>
        </div>
        <DisabledButton />
        <div className="text-[12px] leading-relaxed text-[var(--bh-ink-3)]">
          No verified public phone or email on this record. Add one in
          Airtable (Contact phone or Contact email) and this will light up.
        </div>
      </div>
    );
  }

  // Compact variant for row lists — show just the buttons, no chrome.
  if (variant === "pill") {
    return (
      <div className="flex items-center gap-1.5">
        {hasText && (
          <TextButton href={contacts.text.href} testid="lead-contact-text" label="Text" />
        )}
        {hasEmail && (
          <EmailButton
            href={contacts.email.href}
            testid="lead-contact-email"
            label="Email"
            styleOverride={hasText ? secondary : primary}
          />
        )}
      </div>
    );
  }

  return (
    <div
      className="rounded-md border p-4 space-y-3"
      style={{
        background: "var(--bh-brass-mute)",
        borderColor: "var(--bh-hair-warm)",
      }}
      data-testid="open-in-messages-panel"
    >
      <div className="flex items-center gap-2">
        <MessageSquare size={13} style={{ color: "var(--bh-brass)" }} />
        <span className="bh-eyebrow" style={{ color: "var(--bh-brass)" }}>
          iPhone handoff
        </span>
        {hasBoth && (
          <span
            className="text-[10.5px] px-2 py-0.5 rounded-full font-medium tabular-nums"
            style={{
              background: "var(--bh-surface)",
              border: "1px solid var(--bh-hair-warm)",
              color: "var(--bh-brass)",
            }}
            data-testid="lead-contact-both-badge"
          >
            Text + Email
          </span>
        )}
      </div>

      {/* Buttons */}
      <div className="flex flex-wrap gap-2" data-testid="lead-contact-choices">
        {hasBoth ? (
          <>
            <TextButton
              href={contacts.text.href}
              testid="lead-contact-text"
              label={textedFirst ? "Reopen text" : "Text first"}
              onClick={() => setTextedFirst(true)}
              styleOverride={textedFirst ? secondary : primary}
            />
            <EmailButton
              href={contacts.email.href}
              testid="lead-contact-email"
              label={textedFirst ? "Now open email draft" : "Email"}
              styleOverride={textedFirst ? primary : secondary}
            />
          </>
        ) : hasText ? (
          <TextButton
            href={contacts.text.href}
            testid="lead-contact-text"
            label="Open text draft"
          />
        ) : (
          <EmailButton
            href={contacts.email.href}
            testid="lead-contact-email"
            label="Open email draft"
          />
        )}
      </div>

      {/* Verified recipient(s) */}
      <div className="text-[12px] leading-relaxed text-[var(--bh-ink-2)] space-y-0.5">
        {contacts.text && (
          <div data-testid="lead-contact-text-display">
            <span className="text-[var(--bh-ink-3)]">Text →</span>{" "}
            <strong className="font-medium">{contacts.text.display}</strong>
          </div>
        )}
        {contacts.email && (
          <div data-testid="lead-contact-email-display">
            <span className="text-[var(--bh-ink-3)]">Email →</span>{" "}
            <strong className="font-medium">{contacts.email.display}</strong>
            <span className="text-[var(--bh-ink-3)]">
              {" "}· subject &ldquo;{EMAIL_SUBJECT}&rdquo;
            </span>
          </div>
        )}
      </div>

      {hasBoth && textedFirst && (
        <div
          className="rounded px-2.5 py-1.5 text-[11.5px] leading-relaxed flex items-start gap-1.5"
          style={{
            background: "var(--bh-surface)",
            border: "1px solid var(--bh-hair-warm)",
            color: "var(--bh-ink-2)",
          }}
        >
          <ArrowRight size={11} className="mt-0.5" style={{ color: "var(--bh-brass)" }} />
          <span>
            Text draft opened. When you&rsquo;re done in Messages, tap{" "}
            <span className="font-medium">Now open email draft</span> to hand off to Mail.
          </span>
        </div>
      )}

      <div className="text-[11px] text-[var(--bh-ink-3)] inline-flex items-center gap-1.5">
        <ShieldCheck size={11} style={{ color: "var(--bh-olive)" }} />
        Approval-only · never sends, schedules, or logs an outreach from these buttons
      </div>
    </div>
  );
};

export default OpenInMessages;
