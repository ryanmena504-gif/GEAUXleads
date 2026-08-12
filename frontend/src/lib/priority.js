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

/**
 * hasPremiumFit — is there evidence this is the kind of premium remodel work
 * Ryan wants? Sourced from Airtable's `Premium property or client` checkbox,
 * the AI-derived Opportunity Fit ("Strong"), or a High revenue potential.
 */
export const hasPremiumFit = (opp) => {
  if (!opp) return false;
  if (opp.flag_premium === true) return true;
  const fit = String(opp.opportunity_fit || "").toLowerCase();
  if (fit === "strong") return true;
  const rev = String(opp.revenue_potential || "").toLowerCase();
  if (rev.includes("high")) return true;
  return false;
};

/**
 * contactReady — strict evidence gate for "People to contact today".
 * Every rule must be satisfied. Returns { ready, reasons } so the UI can
 * hide or explain what's missing.
 *
 *  1. Verified public phone OR email on file
 *  2. Premium-fit evidence (see hasPremiumFit)
 *  3. Source URL recorded (we can trace where this came from)
 *  4. Date checked (created_time or last_reviewed on file)
 *  5. No history conflict:
 *      - not closed (Won / Lost / Disqualified)
 *      - not blocked (Do Not Contact / Not interested)
 */
export const contactReady = (opp) => {
  if (!opp) return { ready: false, reasons: ["empty"] };
  const reasons = [];

  const status = String(opp.status || "").toLowerCase();
  if (["disqualified", "lost", "won"].some((s) => status.includes(s))) {
    reasons.push("closed");
  }
  const outreach = String(opp.outreach_status || "").toLowerCase();
  const approval = String(opp.approval_status || "").toLowerCase();
  if (
    outreach.includes("do not contact") ||
    outreach.includes("not interested") ||
    approval.includes("do not contact") ||
    approval.includes("blocked")
  ) {
    reasons.push("blocked");
  }

  const phone = (opp.contact_phone || opp.phone || opp.phone_alt || opp.phone_number || "")
    .toString()
    .trim();
  const email = (opp.contact_email || opp.email || opp.email_alt || "").toString().trim();
  const hasContact = phone.length >= 7 || email.includes("@");
  if (!hasContact) reasons.push("no_contact");

  if (!hasPremiumFit(opp)) reasons.push("not_premium");
  if (!opp.source_url) reasons.push("no_source_url");
  if (!(opp.last_reviewed || opp.created_time)) reasons.push("not_checked");

  return { ready: reasons.length === 0, reasons };
};

/**
 * needsConfirmation — the record's outreach history is ambiguous:
 * something says a contact was sent (checkbox or status), but Ryan never
 * tapped one of the manual result buttons to confirm the outcome. We surface
 * a "Needs confirmation" flag on the detail page so he can resolve it.
 */
export const needsConfirmation = (opp) => {
  if (!opp) return false;
  const outreach = String(opp.outreach_status || "").toLowerCase();
  const sentSignal =
    opp.flag_outreach_sent === true ||
    outreach.includes("sent") ||
    outreach.includes("reply") ||
    outreach.includes("no reply");
  if (!sentSignal) return false;
  const status = String(opp.status || "").toLowerCase();
  const resolved = [
    "conversation started",
    "estimate requested",
    "estimate sent",
    "won",
    "lost",
    "disqualified",
  ].some((s) => status === s);
  return !resolved;
};
