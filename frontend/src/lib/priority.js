// Plain-English priority + contact-state helpers.
//
// The backend still speaks in numeric scores (0–100) and A/B/C/D bands.
// The UI Ryan sees should never expose either. This module converts both
// into "High / Medium / Low" and short reasons a contractor can act on.

const BAND_TO_LEVEL = { A: "High", B: "Medium", C: "Low", D: "Low" };

/**
 * Map a raw priority_band + priority_score to a High / Medium / Low label.
 * Falls back to score thresholds when a band isn't set. Returns null when
 * neither is available so callers can hide the pill entirely.
 */
export const priorityLevel = (band, score) => {
  if (band && BAND_TO_LEVEL[band]) return BAND_TO_LEVEL[band];
  if (typeof score === "number" && !Number.isNaN(score)) {
    if (score >= 80) return "High";
    if (score >= 55) return "Medium";
    return "Low";
  }
  return null;
};

/**
 * One plain-English sentence explaining WHY a lead is high priority.
 * Combines the strongest signals we have: fit, contact readiness, and
 * intent evidence. Kept short so it can render inside a card without wrap.
 */
export const priorityReason = (opp) => {
  if (!opp) return null;
  const level = priorityLevel(opp.priority_band, opp.priority_score);
  const parts = [];
  const fit = opp.opportunity_fit || opp.project_type;
  if (fit && String(fit).toLowerCase() !== "unknown") parts.push(`good fit (${fit})`);
  const reachable = !!(opp.contact_phone || opp.phone || opp.phone_number ||
    opp.contact_email || opp.email || opp.open_approved_message_iphone);
  if (reachable) parts.push("public contact found");
  const evidence = opp.evidence_summary || opp.recommendation_reason;
  if (evidence) parts.push("likely renovation work");
  if (!parts.length) return null;
  const why = parts.join(", ");
  if (level === "High") return `High priority: ${why}.`;
  if (level === "Medium") return `Medium priority: ${why}.`;
  return `Worth watching: ${why}.`;
};

/**
 * Contact-readiness state, expressed as a color + short label.
 *
 *  - green  "Ready to contact"          public phone or email on file
 *  - yellow "Needs a phone or email"    otherwise qualified but no way to reach them
 *  - red    "Not a fit"                 status is Disqualified / Lost / Do Not Contact
 *  - gray   "Keep watching"             everything else (still in research)
 */
export const contactState = (opp) => {
  if (!opp) return { key: "watch", label: "Keep watching", color: "gray" };
  const status = String(opp.status || opp.hunt_status || "").toLowerCase();
  const dnc = (opp.approval_status || opp.outreach_status || "").toLowerCase();
  if (
    status.includes("disqualified") ||
    status.includes("lost") ||
    status.includes("rejected") ||
    dnc.includes("do not contact") ||
    dnc.includes("blocked")
  ) {
    return { key: "not_fit", label: "Not a fit", color: "red" };
  }
  const phone = (opp.contact_phone || opp.phone || opp.phone_number || "").toString().trim();
  const email = (opp.contact_email || opp.email || "").toString().trim();
  const iphone = (opp.open_approved_message_iphone || "").toString().trim();
  const hasContact = (phone && phone.length >= 7) || (email && email.includes("@")) || iphone.toLowerCase().startsWith("sms:");
  if (hasContact) return { key: "ready", label: "Ready to contact", color: "green" };
  const level = priorityLevel(opp.priority_band, opp.priority_score);
  if (level === "High" || level === "Medium") {
    return { key: "needs", label: "Needs a phone or email", color: "yellow" };
  }
  return { key: "watch", label: "Keep watching", color: "gray" };
};
