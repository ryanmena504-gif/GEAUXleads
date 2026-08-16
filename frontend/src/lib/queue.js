// Governed current-state layer helpers.
//
// The Airtable Leads table now has 17 governed fields set by the Make
// classifier. The frontend must NEVER recalculate or override them. This
// module centralizes the small amount of client-side interpretation we do:
// which bucket a record belongs in, how to sort within a bucket, what
// action (if any) is allowed, and how to render the plain-English "why"
// text from Priority Explanation / Current Recommendation.

// Freshness ordering — governed field values, in descending priority.
const FRESHNESS_ORDER = { Current: 0, Aging: 1, Stale: 2, Unknown: 3 };

/**
 * currentQueue — normalized value of the `Current Queue` governed field.
 * Falls back to null when the classifier hasn't tagged the record yet.
 */
export const currentQueue = (opp) => {
  const raw = (opp?.current_queue || "").toString().trim();
  if (!raw) return null;
  const norm = raw.toLowerCase();
  if (norm === "ready to contact") return "Ready to Contact";
  if (norm === "contacted") return "Contacted";
  if (norm === "all projects" || norm === "watch" || norm === "not ready") return "All Projects";
  return raw; // pass through any other governed values verbatim
};

/**
 * queueBucket — which of the three home lists a record belongs to.
 * Ready | Contacted | All. Uses currentQueue as the source of truth.
 * Everything without an explicit "Ready to Contact" or "Contacted" tag
 * falls into All Projects.
 */
export const queueBucket = (opp) => {
  const q = currentQueue(opp);
  if (q === "Ready to Contact") return "ready";
  if (q === "Contacted") return "contacted";
  return "all";
};

/**
 * sortForQueue — Governed Priority Score desc, then Freshness rank.
 * Never uses legacy priority_score / lead_score / status.
 */
export const sortForQueue = (items) =>
  [...(items || [])].sort((a, b) => {
    const scoreA = typeof a.governed_priority_score === "number" ? a.governed_priority_score : -1;
    const scoreB = typeof b.governed_priority_score === "number" ? b.governed_priority_score : -1;
    if (scoreB !== scoreA) return scoreB - scoreA;
    const rankA = FRESHNESS_ORDER[a.freshness] ?? FRESHNESS_ORDER.Unknown;
    const rankB = FRESHNESS_ORDER[b.freshness] ?? FRESHNESS_ORDER.Unknown;
    return rankA - rankB;
  });

/**
 * allowedAction — which draft (if any) this record is eligible for.
 *   "email_first"    → device-native email draft (Ready to Contact only)
 *   "sms_first"      → device-native SMS draft (Ready to Contact only,
 *                       only if the explicit SMS Permission field allows it)
 *   "email_followup" → follow-up email draft (Contacted only)
 *   "sms_followup"   → follow-up SMS draft (Contacted only, SMS Permission)
 *   null             → NO messaging action of any kind (All Projects, or
 *                       Ready-to-Contact records that have neither a public
 *                       email nor SMS permission)
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
 * whyReady — plain-English list of governed signals to show on a Ready row.
 * Never invents anything; each chip only appears when its source field has a
 * value.
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
 * All Projects instead of Ready. Uses Contact Readiness governed field.
 */
export const notReadyReason = (opp) => {
  const cr = (opp.contact_readiness || "").toString().trim();
  if (cr) return cr; // "Needs Public Contact" / "Needs Proof" / "Paused" / etc.
  if (opp.operator_activity && /paused/i.test(opp.operator_activity)) return "Paused";
  return "Not classified yet";
};
