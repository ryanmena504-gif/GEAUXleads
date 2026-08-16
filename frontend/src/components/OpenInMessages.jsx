import React, { useState } from "react";
import { MessageSquare, Mail, ShieldCheck, ArrowRight, Smartphone, ExternalLink, Reply } from "lucide-react";
import { useUserSettings } from "@/hooks/useUserSettings";
import { outreachAllowed } from "@/lib/queue";

/**
 * OpenInMessages — approval-only lead-contact selector, strictly gated by
 * the governed `Current Queue` field.
 *
 *   • Current Queue = "Ready to Contact" → Open Email Draft; Open Text
 *     Draft only when SMS Permission is granted.
 *   • Current Queue = "Contacted"        → Open Follow-Up Draft only.
 *   • Current Queue = "All Projects"     → NOTHING is rendered.
 *
 * Every code path — dashboard, opportunity detail, People to Know cards,
 * Time to Nudge rows, Draft-a-Note drawer footer — flows through this
 * component, so gating here fixes gating everywhere.
 *
 * Draft handoffs are logged separately from confirmed results. Nothing is
 * sent, scheduled, or marked sent when a draft is opened.
 */

// Default sender identity — Ryan's fixed business phone + email.
const DEFAULT_SENDER_EMAIL = "ryanmena@theshirtlesshandyman.com";
const DEFAULT_SENDER_NAME = "Ryan Mena";
const DEFAULT_SENDER_PHONE = "(504) 264-4919";
const DEFAULT_EMAIL_PROVIDER = "apple";
const EMAIL_SUBJECT = "Quick question about your project";
const FOLLOWUP_SUBJECT_PREFIX = "Following up";

const buildEmailComposeUrl = (recipient, body, subject, sender, provider) => {
  if (!recipient) return { href: null, external: false };
  const clean = String(recipient).trim();
  if (!clean.includes("@")) return { href: null, external: false };
  const finalBody = withSignature(body, sender?.name, sender?.email, sender?.phone);
  const finalSubject = subject || EMAIL_SUBJECT;
  const mode = (provider || DEFAULT_EMAIL_PROVIDER).toLowerCase();

  if (mode === "gmail" && sender?.email) {
    const params = new URLSearchParams({
      authuser: sender.email,
      view: "cm",
      fs: "1",
      tf: "1",
      to: clean,
      su: finalSubject,
      body: finalBody,
    });
    return {
      href: `https://mail.google.com/mail/?${params.toString()}`,
      external: true,
    };
  }
  if (mode === "outlook") {
    const params = new URLSearchParams({
      to: clean,
      subject: finalSubject,
      body: finalBody,
    });
    return {
      href: `https://outlook.office.com/mail/deeplink/compose?${params.toString()}`,
      external: true,
    };
  }
  const mailtoParts = [
    `subject=${encodeURIComponent(finalSubject)}`,
    `body=${encodeURIComponent(finalBody)}`,
  ];
  return {
    href: `mailto:${clean}?${mailtoParts.join("&")}`,
    external: false,
  };
};

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

const withSignature = (body, senderName, senderEmail, senderPhone) => {
  const base = (body || "").trim();
  const name = (senderName || DEFAULT_SENDER_NAME).trim();
  const email = (senderEmail || DEFAULT_SENDER_EMAIL).trim();
  const phone = (senderPhone || DEFAULT_SENDER_PHONE).trim();
  const signatureLines = [name, "The Shirtless Handyman"];
  if (phone) signatureLines.push(phone);
  if (email) signatureLines.push(email);
  const signature = `\n\n${signatureLines.join("\n")}`;
  if (!base) return signature.trimStart();
  if (base.endsWith(email)) return base;
  return `${base}${signature}`;
};

const pickMessage = (opp) =>
  opp?.first_contact_message || opp?.first_message || "";

const pickFollowupBody = (opp) =>
  opp?.current_recommendation ||
  "Just checking in — happy to answer any questions or share more detail whenever you have a minute.";

const cleanDisplayPhone = (p) => {
  if (!p) return null;
  const s = String(p).trim();
  return s || null;
};

// SMS Permission is explicit and governed. Only these values unlock a text
// draft; anything else (empty, "No", "unknown", etc.) keeps SMS hidden.
const smsPermitted = (opp) =>
  /yes|granted|opted[\s-]?in|true/i.test((opp?.sms_permission || "").toString());

const buildContacts = ({ opp, senderIdentity, provider, mode }) => {
  const iphoneFormula = (opp?.open_approved_message_iphone || "").toString().trim();
  const phoneRaw = (opp?.contact_phone || opp?.phone || opp?.phone_number || "").toString().trim();
  const emailRaw = (opp?.contact_email || opp?.email || "").toString().trim();
  const isFollowup = mode === "follow_up";
  const subject = isFollowup
    ? `${FOLLOWUP_SUBJECT_PREFIX} · ${opp?.project_type || opp?.name || "your project"}`
    : EMAIL_SUBJECT;
  const body = isFollowup ? pickFollowupBody(opp) : pickMessage(opp);
  const allowSms = isFollowup ? true : smsPermitted(opp); // permission gate

  let textHref = null;
  let textDisplay = null;
  if (allowSms) {
    if (iphoneFormula.toLowerCase().startsWith("sms:")) {
      textHref = sanitizeSmsUrl(iphoneFormula);
      textDisplay = cleanDisplayPhone(phoneRaw) || "iPhone formula";
    } else if (phoneRaw) {
      textHref = buildIosSmsHref(phoneRaw, body);
      textDisplay = cleanDisplayPhone(phoneRaw);
    }
  }

  let emailBundle = { href: null, external: false };
  let emailDisplay = null;
  if (emailRaw && emailRaw.includes("@")) {
    emailBundle = buildEmailComposeUrl(
      emailRaw,
      body,
      subject,
      {
        name: senderIdentity?.name,
        email: senderIdentity?.email,
        phone: senderIdentity?.phone,
      },
      provider,
    );
    emailDisplay = emailRaw;
  }

  return {
    subject,
    text: textHref ? { href: textHref, display: textDisplay } : null,
    email: emailBundle.href
      ? { href: emailBundle.href, display: emailDisplay, external: emailBundle.external }
      : null,
  };
};

/**
 * resolveContacts — kept as a named export for other pages (e.g. Intelligence).
 * Now respects the governed queue: returns empty contacts when Current Queue
 * is not "Ready to Contact" or "Contacted".
 */
export const resolveContacts = (opp, senderIdentity, emailProvider) => {
  const mode = outreachAllowed(opp);
  if (mode === "none") return { text: null, email: null };
  const provider = emailProvider === "outlook" ? "outlook" : (emailProvider || DEFAULT_EMAIL_PROVIDER);
  const c = buildContacts({ opp, senderIdentity, provider, mode });
  return { text: c.text, email: c.email };
};

const btnBase =
  "inline-flex items-center justify-center gap-1.5 rounded-md font-medium " +
  "transition-colors duration-150 whitespace-nowrap no-underline";

const SIZE = {
  md: "h-11 px-4 text-sm",
  sm: "h-8 px-2.5 text-[12px]",
};

const primary = { background: "var(--bh-brass)", color: "var(--bh-surface)" };
const secondary = {
  background: "var(--bh-surface)",
  border: "1px solid var(--bh-hair-strong)",
  color: "var(--bh-ink)",
};

const TextButton = ({ href, testid, label, onClick, styleOverride, size = "md" }) => (
  <a
    href={href}
    data-testid={testid}
    onClick={onClick}
    className={`${btnBase} ${SIZE[size]}`}
    style={styleOverride || primary}
  >
    <MessageSquare size={size === "sm" ? 12 : 14} /> {label}
  </a>
);

const EmailButton = ({ href, testid, label, onClick, styleOverride, size = "md", external = false, icon: Icon = Mail }) => (
  <a
    href={href}
    data-testid={testid}
    onClick={onClick}
    className={`${btnBase} ${SIZE[size]}`}
    style={styleOverride || primary}
    {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
  >
    <Icon size={size === "sm" ? 12 : 14} /> {label}
    {external && <ExternalLink size={size === "sm" ? 10 : 11} className="opacity-70" />}
  </a>
);

/**
 * @param {object} props
 * @param {object} props.opportunity — full opportunity DTO
 * @param {"pill"|"panel"} [props.variant]
 */
export const OpenInMessages = ({ opportunity, variant = "panel" }) => {
  const { settings } = useUserSettings();
  // All hooks live at the top so Rules of Hooks are respected regardless
  // of which governed branch renders below.
  const [textedFirst, setTextedFirst] = useState(false);
  const senderIdentity = {
    name: settings?.sender_name,
    email: settings?.sender_email,
    phone: settings?.sender_phone,
  };
  const emailProvider = (settings?.email_provider || DEFAULT_EMAIL_PROVIDER).toLowerCase() === "outlook"
    ? "outlook"
    : "apple";
  const providerLabel =
    emailProvider === "gmail" ? "Gmail"
    : emailProvider === "outlook" ? "Outlook"
    : "Apple Mail";

  const mode = outreachAllowed(opportunity);

  // GLOBAL GATE #1 — All Projects (or unclassified): render nothing anywhere.
  if (mode === "none") return null;

  const contacts = buildContacts({
    opp: opportunity,
    senderIdentity,
    provider: emailProvider,
    mode,
  });
  const hasText = !!contacts.text;
  const hasEmail = !!contacts.email;
  const emailIsExternal = !!contacts.email?.external;

  // GLOBAL GATE #2 — Contacted: exactly ONE follow-up draft button. No
  // Text / Email / Contact them / Draft a Note controls, ever.
  if (mode === "follow_up") {
    // Prefer email for follow-ups; fall back to SMS only if there is no
    // email on file. If neither channel is available, render nothing.
    if (!hasEmail && !hasText) return null;
    const useEmail = hasEmail;
    const href = useEmail ? contacts.email.href : contacts.text.href;
    const testid = useEmail ? "open-followup-email-draft" : "open-followup-sms-draft";
    const label = useEmail ? "Open Follow-Up Draft" : "Open Follow-Up Text Draft";
    const Icon = useEmail ? Reply : MessageSquare;
    const external = useEmail && emailIsExternal;
    // No onClick handler — opening a native draft must cause ZERO API
    // writes. The handoff audit log is only recorded via the explicit
    // "I sent it" outcome in ContactResults, never as a side effect.

    if (variant === "pill") {
      return (
        <div className="flex items-center gap-1.5" data-testid="lead-followup-pill">
          <EmailButton
            href={href}
            testid={testid}
            label={label}
            external={external}
            size="sm"
            icon={Icon}
          />
        </div>
      );
    }
    return (
      <div
        className="rounded-md border p-4 space-y-3"
        style={{ background: "var(--bh-brass-mute)", borderColor: "var(--bh-hair-warm)" }}
        data-testid="open-followup-panel"
      >
        <div className="flex items-center gap-2">
          <Reply size={13} style={{ color: "var(--bh-brass)" }} />
          <span className="bh-eyebrow" style={{ color: "var(--bh-brass)" }}>
            Follow up
          </span>
          {opportunity?.contact_state && (
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
          )}
        </div>
        <div className="flex flex-wrap gap-2" data-testid="lead-followup-choices">
          <EmailButton
            href={href}
            testid={testid}
            label={label}
            external={external}
            icon={Icon}
          />
        </div>
        <div className="text-[11.5px] leading-relaxed text-[var(--bh-ink-2)]">
          {useEmail
            ? <>Opens a draft in {providerLabel}. Nothing sends until you press Send yourself.</>
            : <>Opens Messages on this device. Nothing sends until you press Send yourself.</>}
        </div>
        <div className="text-[11px] text-[var(--bh-ink-3)] inline-flex items-center gap-1.5">
          <ShieldCheck size={11} style={{ color: "var(--bh-olive)" }} />
          Follow-up draft only. First-contact controls stay hidden on Contacted records.
        </div>
      </div>
    );
  }

  // Ready to Contact from here on. Existing first-contact UI.
  const hasBoth = hasText && hasEmail;

  // Opening a draft must NOT cause any backend write. The "I sent it"
  // outcome button in ContactResults is the only path that records a
  // handoff — and only after Ryan explicitly confirms he sent something.
  const onTextTap = () => {
    if (hasBoth) setTextedFirst(true);
  };
  const onEmailTap = () => { /* no-op — draft opens with zero API writes */ };

  // Ready record with no channel at all — do not render an empty gate.
  if (!hasText && !hasEmail) return null;

  if (variant === "pill") {
    return (
      <div className="flex items-center gap-1.5" data-testid="lead-contact-pill">
        {hasEmail && (
          <EmailButton
            href={contacts.email.href}
            testid="open-email-draft"
            label="Open Email Draft"
            onClick={onEmailTap}
            size="sm"
            external={emailIsExternal}
          />
        )}
        {hasText && (
          <TextButton
            href={contacts.text.href}
            testid="open-text-draft"
            label="Open Text Draft"
            onClick={onTextTap}
            styleOverride={hasEmail ? secondary : primary}
            size="sm"
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
          Contact them
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
            Email + Text
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-2" data-testid="lead-contact-choices">
        {hasBoth ? (
          <>
            <EmailButton
              href={contacts.email.href}
              testid="open-email-draft"
              label={textedFirst ? "Reopen email draft" : "Open Email Draft"}
              onClick={onEmailTap}
              styleOverride={textedFirst ? secondary : primary}
              external={emailIsExternal}
            />
            <TextButton
              href={contacts.text.href}
              testid="open-text-draft"
              label={textedFirst ? "Now open text draft" : "Open Text Draft"}
              onClick={onTextTap}
              styleOverride={textedFirst ? primary : secondary}
            />
          </>
        ) : hasEmail ? (
          <EmailButton
            href={contacts.email.href}
            testid="open-email-draft"
            label="Open Email Draft"
            onClick={onEmailTap}
            external={emailIsExternal}
          />
        ) : (
          <TextButton
            href={contacts.text.href}
            testid="open-text-draft"
            label="Open Text Draft"
            onClick={onTextTap}
          />
        )}
      </div>

      <div className="space-y-1" data-testid="handoff-helper">
        {hasEmail && emailIsExternal && (
          <div className="text-[11.5px] leading-relaxed text-[var(--bh-ink-2)] inline-flex items-center gap-1.5" data-testid="handoff-email-pin">
            <Mail size={11} strokeWidth={1.75} style={{ color: "var(--bh-brass)" }} />
            Emails always send from{" "}
            <strong className="font-medium">{senderIdentity.email || DEFAULT_SENDER_EMAIL}</strong>{" "}
            via {providerLabel}.
          </div>
        )}
        {hasEmail && !emailIsExternal && (
          <div className="text-[11.5px] leading-relaxed text-[var(--bh-ink-3)]" data-testid="handoff-email-mailto">
            Opens a draft in your default mail app. Make sure it&rsquo;s signed
            into <strong className="font-medium">{senderIdentity.email || DEFAULT_SENDER_EMAIL}</strong>.
          </div>
        )}
        {hasText && (
          <div className="text-[11px] leading-relaxed text-[var(--bh-ink-3)] inline-flex items-center gap-1.5" data-testid="handoff-iphone-hint">
            <Smartphone size={11} strokeWidth={1.75} style={{ color: "var(--bh-brass)" }} />
            Text drafts open Messages on this device. SMS Permission on file: {opportunity?.sms_permission || "not set"}.
          </div>
        )}
      </div>

      <div className="text-[12px] leading-relaxed text-[var(--bh-ink-2)] space-y-0.5">
        {contacts.email && (
          <div data-testid="lead-contact-email-display">
            <span className="text-[var(--bh-ink-3)]">Email →</span>{" "}
            <strong className="font-medium">{contacts.email.display}</strong>
            <span className="text-[var(--bh-ink-3)]">
              {" "}· subject &ldquo;{contacts.subject}&rdquo;
            </span>
          </div>
        )}
        {contacts.text && (
          <div data-testid="lead-contact-text-display">
            <span className="text-[var(--bh-ink-3)]">Text →</span>{" "}
            <strong className="font-medium">{contacts.text.display}</strong>
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
        Nothing sends until you press Send yourself.
      </div>
    </div>
  );
};

export default OpenInMessages;
