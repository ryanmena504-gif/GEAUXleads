// Governed current-state layer — strict read-through of Airtable + Make.
//
// The Airtable Leads table carries 17 governed fields set by the Make
// classifier. The frontend NEVER recalculates, infers, or overrides them.
// Every helper below is an EXACT string equality on a single governed
// field — no toLowerCase, no fuzzy match, no legacy-field fallback, no
// phone/email inference. If the classifier hasn't tagged a record, it
// belongs in All Projects. Full stop.
//
// Field ownership:
//   • Current Queue     → controls which of the three lists a record shows in
//   • Contact Readiness → controls Paused / not-ready reason on All Projects
//   • Contact State     → follow-up / lifecycle context on Contacted rows
//   • Freshness         → tiebreak for sort order (Current → Aging → Stale)
//
// Opening an email or text draft writes nothing and changes no state.

// The exact governed values that place a record into the Ready / Contacted
// lists. Anything else (including empty, unclassified, "Watch", "Not Ready")
// lands in All Projects.
const READY = "Ready to Contact";
const CONTACTED = "Contacted";

// Freshness sort rank — only exact governed values count.
const FRESHNESS_ORDER = { Current: 0, Aging: 1, Stale: 2 };

/**
 * currentQueue — the raw governed `Current Queue` string, verbatim.
 * Returns null if the field is missing or non-string.
 */
export const currentQueue = (opp) => {
  const raw = opp?.current_queue;
  return typeof raw === "string" && raw ? raw : null;
};

/**
 * queueBucket — which of the three home lists a record belongs to.
 * Strict exact-string match on Current Queue. No fuzzy match.
 *   "Ready to Contact" → "ready"
 *   "Contacted"        → "contacted"
 *   anything else      → "all"
 */
export const queueBucket = (opp) => {
  const q = currentQueue(opp);
  if (q === READY) return "ready";
  if (q === CONTACTED) return "contacted";
  return "all";
};

/**
 * sortForQueue — Governed Priority Score desc, tiebreak Freshness rank asc.
 * Never uses legacy priority_score / lead_score / status.
 */
export const sortForQueue = (items) =>
  [...(items || [])].sort((a, b) => {
    const scoreA = typeof a.governed_priority_score === "number" ? a.governed_priority_score : -1;
    const scoreB = typeof b.governed_priority_score === "number" ? b.governed_priority_score : -1;
    if (scoreB !== scoreA) return scoreB - scoreA;
    const rankA = FRESHNESS_ORDER[a.freshness] ?? 99;
    const rankB = FRESHNESS_ORDER[b.freshness] ?? 99;
    return rankA - rankB;
  });

/**
 * allowedAction — which draft (if any) this record is eligible for.
 * The GATE is strict Current Queue. The choice between email and SMS is a
 * presentation-only detail — it selects which mailto:/sms: URL to build.
 * Opening either draft writes nothing and changes no state.
 *
 *   "email_first"    → device-native email draft (Ready to Contact only)
 *   "sms_first"      → device-native SMS draft (Ready to Contact only,
 *                       only if SMS Permission is explicitly granted)
 *   "email_followup" → follow-up email draft (Contacted only)
 *   "sms_followup"   → follow-up SMS draft (Contacted only, SMS Permission)
 *   null             → no messaging control rendered
 */
export const allowedAction = (opp) => {
  const bucket = queueBucket(opp);
  if (bucket === "all") return null;
  const hasEmail = /@/.test(opp?.email || opp?.email_alt || "");
  const smsPermitted =
    /yes|granted|opted[\s-]?in|true/i.test((opp?.sms_permission || "").toString());
  if (bucket === "ready") {
    if (hasEmail) return "email_first";
    if (smsPermitted) return "sms_first";
    return null;
  }
  // bucket === "contacted"
  if (hasEmail) return "email_followup";
  if (smsPermitted) return "sms_followup";
  return null;
};

/**
 * whyReady — plain-English list of governed signals shown on a Ready row.
 * Each chip only appears when its source governed field has a value; nothing
 * is invented and no legacy field is consulted.
 */
export const whyReady = (opp) => {
  const chips = [];
  if (opp.money_signal) chips.push({ label: "Money Signal", value: opp.money_signal });
  if (opp.premium_fit) chips.push({ label: "Premium Fit", value: opp.premium_fit });
  if (opp.evidence_status) chips.push({ label: "Evidence", value: opp.evidence_status });
  if (opp.freshness) chips.push({ label: "Freshness", value: opp.freshness });
  return chips;
};

/**
 * notReadyReason — plain-English explanation of why a record is in
 * All Projects instead of Ready. Reads Contact Readiness verbatim.
 * NEVER falls back to operator_activity, contact_state, or any legacy field.
 */
export const notReadyReason = (opp) => {
  const cr = opp?.contact_readiness;
  if (typeof cr === "string" && cr.trim()) return cr.trim();
  return "Not classified yet";
};
