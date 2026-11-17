/**
 * Today-page list rules (2026-11-16 review).
 *
 *   • Today only shows leads Ryan can actually reach: a phone or an email
 *     on file (hasContactChannel). Everything else stays in Opportunities,
 *     the door-hanger route, or the research lists.
 *   • A lead that wrote back goes to the top in "Replied, answer these",
 *     ahead of the follow-up queue, so a reply never waits behind cold
 *     outreach again (M&Z Renovations waited from Aug 25).
 */
import { hasContactChannel, pickEmail, pickPhone } from "./contact";

export const CLOSED_STATUSES = new Set(["Won", "Lost", "Disqualified"]);

export const isClosed = (opp) => CLOSED_STATUSES.has(opp?.status);

export const isReachable = (opp) => hasContactChannel(opp);

const REPLIED_OUTREACH = /^(replied|reply received|estimate requested)\b/i;

/** Open lead whose outreach status says they answered and Ryan owes the next move. */
export const isRepliedLead = (opp) => {
  if (!opp || isClosed(opp)) return false;
  if (opp.status === "Estimate sent") return false;
  const os = String(opp.outreach_status || "").trim();
  return REPLIED_OUTREACH.test(os) || Boolean(opp.flag_reply_received);
};

/** Replied leads, oldest reply first — the longest wait gets answered first. */
export const repliedQueue = (items) =>
  (items || [])
    .filter(isRepliedLead)
    .sort((a, b) =>
      String(a.date_replied || a.message_sent_date || "9999").localeCompare(
        String(b.date_replied || b.message_sent_date || "9999"),
      ),
    );

export const telHref = (opp) => {
  const p = pickPhone(opp).replace(/[^\d+]/g, "");
  return p ? `tel:${p}` : null;
};

export const smsHref = (opp) => {
  const p = pickPhone(opp).replace(/[^\d+]/g, "");
  return p ? `sms:${p}` : null;
};

export const mailHref = (opp) => {
  const e = pickEmail(opp);
  return e ? `mailto:${e}` : null;
};
