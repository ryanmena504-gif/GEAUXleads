import React, { useState } from "react";
import { MessageSquare, Mail, Lock, ShieldCheck, ArrowRight, Smartphone, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";
import { useUserSettings } from "@/hooks/useUserSettings";

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

// Default sender identity — Ryan's fixed business phone + email for The
// Shirtless Handyman. Ryan can override these in Settings, but every email
// draft is signed with this identity by default. Bloodhound never CONNECTS
// to any account; the values just appear inside the mailto: body so the
// recipient sees the right contact info.
const DEFAULT_SENDER_EMAIL = "ryanmena@theshirtlesshandyman.com";
const DEFAULT_SENDER_NAME = "Ryan Mena";
const DEFAULT_SENDER_PHONE = "(504) 264-4919";
const DEFAULT_EMAIL_PROVIDER = "gmail";
const EMAIL_SUBJECT = "Quick question about your project";

/**
 * Build the email-compose URL for the configured provider.
 *
 * Gmail  — https://mail.google.com/mail/?authuser=<sender>&view=cm&... — the
 *          `authuser` parameter forces Gmail Web to compose from Ryan's
 *          business account regardless of which browser or device he uses.
 *          On mobile, this URL deep-links into the Gmail app with the same
 *          account pinned.
 * Outlook — https://outlook.office.com/mail/deeplink/compose?... — opens
 *          Outlook Web with the recipient / subject / body pre-filled.
 *          Uses whichever Microsoft account is signed in; if multiple, the
 *          user picks. There is no reliable equivalent of Gmail's authuser.
 * Apple / mailto — the classic behaviour: uses whatever default mail app is
 *          set on the current device. Correct for iPhone (uses Ryan's
 *          business email if that's his default account), unpredictable on
 *          laptops. Included as a fallback and for Apple-Mail-only users.
 */
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
  // Apple Mail / default mail app — plain mailto:.
  const mailtoParts = [
    `subject=${encodeURIComponent(finalSubject)}`,
    `body=${encodeURIComponent(finalBody)}`,
  ];
  return {
    href: `mailto:${clean}?${mailtoParts.join("&")}`,
    external: false,
  };
};

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

// mailto: signature. Includes the sender's name, business, phone, and
// email so it's visible in the composed draft — iPhone/Mac Mail can't be
// forced to a specific From account via mailto, so this at least makes
// sure the recipient sees the right contact info.
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

const buildMailtoHref = (email) => {
  if (!email) return null;
  const clean = String(email).trim();
  if (!clean.includes("@")) return null;
  const params = [
    `subject=${encodeURIComponent(EMAIL_SUBJECT)}`,
  ];
  return `mailto:${clean}?${params.join("&")}`;
};

const buildMailtoWithBody = (email, body, senderName, senderEmail, senderPhone) => {
  if (!email) return null;
  const clean = String(email).trim();
  if (!clean.includes("@")) return null;
  const params = [
    `subject=${encodeURIComponent(EMAIL_SUBJECT)}`,
    `body=${encodeURIComponent(withSignature(body, senderName, senderEmail, senderPhone))}`,
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

export const resolveContacts = (opp, senderIdentity, emailProvider) => {
  if (!opp) return { text: null, email: null };
  const iphoneFormula = (opp.open_approved_message_iphone || "").toString().trim();
  const phoneRaw = (opp.contact_phone || opp.phone || opp.phone_number || "").toString().trim();
  const emailRaw = (opp.contact_email || opp.email || "").toString().trim();
  const message = pickMessage(opp);
  const senderName = senderIdentity?.name;
  const senderEmail = senderIdentity?.email;
  const senderPhone = senderIdentity?.phone;
  const provider = emailProvider || DEFAULT_EMAIL_PROVIDER;

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

  let emailBundle = { href: null, external: false };
  let emailDisplay = null;
  if (emailRaw && emailRaw.includes("@")) {
    emailBundle = buildEmailComposeUrl(
      emailRaw,
      message,
      EMAIL_SUBJECT,
      { name: senderName, email: senderEmail, phone: senderPhone },
      provider,
    );
    emailDisplay = emailRaw;
  }

  return {
    text: textHref ? { href: textHref, display: textDisplay } : null,
    email: emailBundle.href
      ? { href: emailBundle.href, display: emailDisplay, external: emailBundle.external }
      : null,
  };
};

const btnBase =
  "inline-flex items-center justify-center gap-1.5 rounded-md font-medium " +
  "transition-colors duration-150 whitespace-nowrap no-underline";

const SIZE = {
  md: "h-11 px-4 text-sm",
  sm: "h-8 px-2.5 text-[12px]",
};

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

const EmailButton = ({ href, testid, label, onClick, styleOverride, size = "md", external = false }) => (
  <a
    href={href}
    data-testid={testid}
    onClick={onClick}
    className={`${btnBase} ${SIZE[size]}`}
    style={styleOverride || primary}
    {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
  >
    <Mail size={size === "sm" ? 12 : 14} /> {label}
    {external && <ExternalLink size={size === "sm" ? 10 : 11} className="opacity-70" />}
  </a>
);

const DisabledButton = ({ size = "md" }) => (
  <button
    type="button"
    disabled
    data-testid="open-in-messages-disabled"
    className={`${btnBase} ${SIZE[size]} cursor-not-allowed`}
    style={disabled}
  >
    <Lock size={size === "sm" ? 12 : 14} /> Public contact needed
  </button>
);

/**
 * @param {object} props
 * @param {object} props.opportunity — full opportunity DTO
 * @param {"pill"|"panel"|"row"} [props.variant]
 */
export const OpenInMessages = ({ opportunity, variant = "panel" }) => {
  const { settings } = useUserSettings();
  const senderIdentity = {
    name: settings?.sender_name,
    email: settings?.sender_email,
    phone: settings?.sender_phone,
  };
  const emailProvider = (settings?.email_provider || DEFAULT_EMAIL_PROVIDER).toLowerCase();
  const contacts = resolveContacts(opportunity, senderIdentity, emailProvider);
  const hasText = !!contacts.text;
  const hasEmail = !!contacts.email;
  const hasBoth = hasText && hasEmail;
  const emailIsExternal = !!contacts.email?.external;
  const providerLabel =
    emailProvider === "gmail" ? "Gmail"
    : emailProvider === "outlook" ? "Outlook"
    : "Apple Mail";

  // Once the user taps a TEXT handoff on a BOTH lead, reveal a follow-up
  // "Open email draft" primary button. Do NOT auto-launch Mail — the user
  // presses it themselves after returning from Messages.
  const [textedFirst, setTextedFirst] = useState(false);

  // Fire-and-forget handoff logger. We deliberately do NOT block navigation
  // (no preventDefault, no await), so the sms:/mailto:/Gmail-compose URL
  // still opens on the same user gesture. If the POST fails we swallow it —
  // this is a log, not a gate.
  const logTap = (channel, recipient) => {
    const oppId = opportunity?.id;
    if (!oppId) return;
    try {
      api
        .logHandoff(oppId, {
          opportunity_id: oppId,
          opportunity_name: opportunity?.name,
          channel,
          recipient: recipient || null,
        })
        .catch(() => {});
    } catch {
      /* never break the native handoff */
    }
  };

  const onTextTap = () => {
    logTap("text", contacts.text?.display);
    if (hasBoth) setTextedFirst(true);
  };
  const onEmailTap = () => {
    logTap("email", contacts.email?.display);
  };

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
            Contact them
          </span>
        </div>
        <DisabledButton />
        <div className="text-[12px] leading-relaxed text-[var(--bh-ink-3)]">
          Add a phone number or email for this person and this button will
          light up.
        </div>
      </div>
    );
  }

  // Compact variant for row lists — show just the buttons, no chrome.
  if (variant === "pill") {
    return (
      <div className="flex items-center gap-1.5" data-testid="lead-contact-pill">
        {hasText && (
          <TextButton
            href={contacts.text.href}
            testid="lead-contact-text"
            label="Text"
            size="sm"
          />
        )}
        {hasEmail && (
          <EmailButton
            href={contacts.email.href}
            testid="lead-contact-email"
            label="Email"
            styleOverride={hasText ? secondary : primary}
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
              label={textedFirst ? "Reopen text draft" : "Contact by text"}
              onClick={onTextTap}
              styleOverride={textedFirst ? secondary : primary}
            />
            <EmailButton
              href={contacts.email.href}
              testid="lead-contact-email"
              label={textedFirst ? "Now open email draft" : "Contact by email"}
              onClick={onEmailTap}
              styleOverride={textedFirst ? primary : secondary}
              external={emailIsExternal}
            />
          </>
        ) : hasText ? (
          <TextButton
            href={contacts.text.href}
            testid="lead-contact-text"
            label="Contact them"
            onClick={onTextTap}
          />
        ) : (
          <EmailButton
            href={contacts.email.href}
            testid="lead-contact-email"
            label="Contact them"
            onClick={onEmailTap}
            external={emailIsExternal}
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
            Texts open Messages on this device. Open Bloodhound on your iPhone to text from{" "}
            {senderIdentity.phone || DEFAULT_SENDER_PHONE}.
          </div>
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
        Nothing sends until you press Send yourself.
      </div>
    </div>
  );
};

export default OpenInMessages;
