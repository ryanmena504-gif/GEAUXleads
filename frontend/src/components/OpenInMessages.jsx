import React from "react";
import { MessageSquare, Mail, Lock, ShieldCheck } from "lucide-react";

/**
 * OpenInMessages — iPhone handoff. NO automation, NO backend write.
 *
 * Priority (matches the user's spec):
 *   1. If Airtable's `Open approved message iPhone` formula returns an
 *      `sms:` URL, render it verbatim as the button href.
 *   2. Else, if there's a Contact phone + a message text, build an
 *      `sms:` link locally with the URL-encoded body.
 *   3. Else, if there's a Contact email, render a `mailto:` draft with the
 *      subject and body prefilled — labeled OPEN EMAIL DRAFT.
 *   4. Else, render a disabled "PUBLIC CONTACT NEEDED" button.
 *
 * Tapping the button on iPhone opens Apple Messages / Mail with the draft
 * pre-populated. The user hits Send themselves inside the native app.
 * Bloodhound never sends, schedules, or persists a status change from this.
 */

// Sanitize an sms: URL so iOS Safari will actually open Messages.
// iOS is strict: the phone must be digits (with an optional leading `+`)
// only — no spaces, dashes, or parens — otherwise it throws "Failed to
// load" and never hands off to the Messages app. We honor whatever body
// the Airtable formula produced but rebuild the phone portion.
const sanitizeSmsUrl = (rawUrl) => {
  if (typeof rawUrl !== "string") return null;
  const trimmed = rawUrl.trim();
  if (!/^sms:/i.test(trimmed)) return null;
  const rest = trimmed.slice(4); // drop "sms:"
  // Split on the first '?' or '&' — whichever comes first — into phone / query.
  const qIdx = rest.search(/[?&]/);
  const rawPhone = qIdx === -1 ? rest : rest.slice(0, qIdx);
  const query = qIdx === -1 ? "" : rest.slice(qIdx + 1);
  // Keep only digits and a leading `+`.
  let phone = rawPhone.replace(/[^\d+]/g, "");
  if (phone.startsWith("+")) {
    phone = "+" + phone.slice(1).replace(/\+/g, "");
  } else {
    phone = phone.replace(/\+/g, "");
  }
  if (!phone) return null;
  // Always use the `&body=` form — it works on every iOS version since 8,
  // whereas `?body=` fails on some older Message app builds.
  return query ? `sms:${phone}&${query.replace(/^\?/, "")}` : `sms:${phone}`;
};

// iOS Safari-friendly SMS href built from raw fields.
const buildIosSmsHref = (phone, body) => {
  if (!phone) return null;
  const cleanPhone = String(phone).replace(/[^\d+]/g, "");
  if (!cleanPhone) return null;
  const q = body ? `&body=${encodeURIComponent(String(body).trim())}` : "";
  return `sms:${cleanPhone}${q}`;
};

const buildMailtoHref = (email, subject, body) => {
  if (!email) return null;
  const clean = String(email).trim();
  if (!clean.includes("@")) return null;
  const parts = [];
  if (subject) parts.push(`subject=${encodeURIComponent(subject.trim())}`);
  if (body) parts.push(`body=${encodeURIComponent(String(body).trim())}`);
  return `mailto:${clean}${parts.length ? `?${parts.join("&")}` : ""}`;
};

const pickMessage = (opp) =>
  opp?.first_contact_message ||
  opp?.first_message ||
  "";

const pickSubject = (opp) => {
  const project = opp?.project_type || opp?.opportunity_type;
  if (project) return `Following up on your ${project}`;
  return "Following up";
};

export const resolveOpenInMessages = (opp) => {
  if (!opp) return { mode: "none" };
  const iphoneFormula = (opp.open_approved_message_iphone || "").toString().trim();
  const phone = (opp.contact_phone || opp.phone || opp.phone_number || "").toString().trim();
  const email = (opp.contact_email || opp.email || "").toString().trim();
  const message = pickMessage(opp);
  const subject = pickSubject(opp);

  if (iphoneFormula.toLowerCase().startsWith("sms:")) {
    // Airtable's formula puts parens + spaces into the phone which iOS
    // rejects with "Failed to load". Sanitize before handoff.
    const cleaned = sanitizeSmsUrl(iphoneFormula);
    if (cleaned) {
      return { mode: "sms_formula", href: cleaned, source: phone || "iPhone formula" };
    }
  }
  if (phone && message) {
    const href = buildIosSmsHref(phone, message);
    if (href) return { mode: "sms_local", href, source: phone };
  }
  if (email) {
    const href = buildMailtoHref(email, subject, message);
    if (href) return { mode: "email", href, source: email };
  }
  return { mode: "none" };
};

const btnBase =
  "inline-flex items-center justify-center gap-1.5 h-11 px-4 rounded-md text-sm font-medium " +
  "transition-colors duration-150 whitespace-nowrap";

/**
 * @param {object} props
 * @param {object} props.opportunity  — full opportunity DTO
 * @param {"pill"|"panel"|"row"} [props.variant]
 *   - "pill"  – compact button for lists/rows
 *   - "row"   – button + source hint (default)
 *   - "panel" – full card with header + source hint (for detail pages)
 */
export const OpenInMessages = ({ opportunity, variant = "row" }) => {
  const resolved = resolveOpenInMessages(opportunity);
  const isSms = resolved.mode === "sms_formula" || resolved.mode === "sms_local";
  const isEmail = resolved.mode === "email";
  const disabled = resolved.mode === "none";

  const label = isSms
    ? "Open in Messages"
    : isEmail
    ? "Open Email Draft"
    : "Public contact needed";

  const testid = isSms
    ? "open-in-messages"
    : isEmail
    ? "open-email-draft"
    : "open-in-messages-disabled";

  const Icon = isEmail ? Mail : isSms ? MessageSquare : Lock;

  const button = disabled ? (
    <button
      type="button"
      disabled
      data-testid={testid}
      className={btnBase + " cursor-not-allowed"}
      style={{
        background: "var(--bh-surface-2)",
        border: "1px solid var(--bh-hair)",
        color: "var(--bh-ink-mute)",
      }}
    >
      <Icon size={14} />
      {label}
    </button>
  ) : (
    <a
      href={resolved.href}
      data-testid={testid}
      // No target=_blank — iOS handoff to Messages/Mail requires same-window
      // navigation to trigger the native protocol handler.
      className={btnBase + " no-underline"}
      style={{
        background: "var(--bh-brass)",
        color: "var(--bh-surface)",
      }}
    >
      <Icon size={14} />
      {label}
    </a>
  );

  const hint = disabled ? (
    <span>
      No verified public phone or email on this record. Add one in Airtable
      (Contact phone or Contact email) and this button will light up.
    </span>
  ) : (
    <span>
      Handoff to your iPhone — <strong className="font-medium">{resolved.source}</strong>.
      You press Send yourself; Bloodhound never sends.
    </span>
  );

  if (variant === "pill") {
    return button;
  }

  if (variant === "panel") {
    return (
      <div
        className="rounded-md border p-4 space-y-2"
        style={{
          background: disabled ? "var(--bh-surface-2)" : "var(--bh-brass-mute)",
          borderColor: disabled ? "var(--bh-hair)" : "var(--bh-hair-warm)",
        }}
        data-testid="open-in-messages-panel"
      >
        <div className="flex items-center gap-2">
          <MessageSquare size={13} style={{ color: disabled ? "var(--bh-ink-mute)" : "var(--bh-brass)" }} />
          <span
            className="bh-eyebrow"
            style={{ color: disabled ? "var(--bh-ink-mute)" : "var(--bh-brass)" }}
          >
            iPhone handoff
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {button}
          <div className="text-[12px] leading-relaxed text-[var(--bh-ink-2)] flex-1 min-w-[160px]">
            {hint}
          </div>
        </div>
        <div className="text-[11px] text-[var(--bh-ink-3)] inline-flex items-center gap-1.5">
          <ShieldCheck size={11} style={{ color: "var(--bh-olive)" }} />
          Approval-only · never sends, schedules, or logs an outreach from this button
        </div>
      </div>
    );
  }

  // "row" default
  return (
    <div className="space-y-1.5">
      {button}
      <div className="text-[11px] leading-relaxed text-[var(--bh-ink-3)]">{hint}</div>
    </div>
  );
};

export default OpenInMessages;
