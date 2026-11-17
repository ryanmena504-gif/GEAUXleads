/**
 * Outreach copy rules from the 2026-11-16 GEAUXleads review. Every draft
 * builder routes stored (Airtable) and hardcoded copy through these so:
 *
 *   1. Listing-agent pitches never point at a seller's price cuts, days on
 *      market or motivation, and never ask the seller to remodel. They
 *      offer a fast bath quote for a buyer instead (LISTING_AGENT_TEMPLATE).
 *   2. Microcement is never promised to go "over existing tile, no demo day"
 *      as a sure thing — only "often … once I've checked it's solid."
 *   3. Follow-ups give the reader something to answer: recent work, photos,
 *      or a sample board drop-off.
 *
 * `softenDraftClaims` and `mentionsListingPressure` have a Python mirror in
 * backend/services/draft_safety.py. Keep the two in sync.
 */

export const TILE_CONDITIONAL = "often goes over existing tile once I've checked it's solid";

const TILE_CLAIMS = [
  /\b(?:it\s+)?goes\s+(?:right\s+)?over\s+(?:the\s+|your\s+)?existing\s+tile(?:\s*(?:,|—|-|–)\s*(?:so\s+)?no\s+demo(?:\s+day)?)?/i,
  /\bright\s+over\s+(?:the\s+|your\s+)?existing\s+tile/i,
];
const LEFTOVER_NO_DEMO = /\s*(?:,|—|-|–)\s*no\s+demo\s+day\b/gi;

/** Rewrite unconditional "over existing tile / no demo day" promises. Idempotent. */
export const softenDraftClaims = (text) => {
  if (!text || typeof text !== "string") return text || "";
  let s = text;
  // Already conditional ("…once I've checked it's solid") → leave the tile line alone.
  if (!/once i['’]ve checked it['’]s solid/i.test(s)) {
    for (const re of TILE_CLAIMS) {
      if (re.test(s)) {
        s = s.replace(re, TILE_CONDITIONAL);
        break;
      }
    }
  }
  return s.replace(LEFTOVER_NO_DEMO, "");
};

const LISTING_PRESSURE = [
  /\$\s?\d[\d,]*k?\s+(?:in\s+)?cuts?\b/i,
  /\bcut\s+\$\s?\d/i,
  /\bprice\s+(?:cut|drop|reduction)s?\b/i,
  /\bcut\s+(?:\w+\s+)?(?:times|twice)\b/i,
  /\bsitting\s+\d+\s+days\b/i,
  /\b(?:on the market|on zillow|on redfin)\s+\d+\s+days\b/i,
  /\bmotivated\s+seller\b/i,
  /\brelisted\b|\bsecond run\b|\brough tenant\b/i,
];

/** True when a draft points at a listing's price cuts / days on market / seller. */
export const mentionsListingPressure = (text) =>
  Boolean(text) && LISTING_PRESSURE.some((re) => re.test(String(text)));

/**
 * isListingAgentLead — a lead whose contact is the listing agent on a home
 * for sale (Lane-1 stale listings). Detected from the record itself: the
 * morning staging writes "stale listing" into Notes, and the stored drafts
 * open with "Saw your <street> listing".
 */
export const isListingAgentLead = (opp) => {
  if (!opp) return false;
  const notes = String(opp.notes || "");
  const draft = String(opp.draft_outreach_body || opp.first_message || "");
  if (/stale listing/i.test(notes)) return true;
  return /\bsaw your \w[\w .'-]* listing\b/i.test(draft);
};

/** "8713 Cohn St, New Orleans, LA" → "Cohn St". Empty when unknown. */
export const streetName = (address) => {
  if (!address || typeof address !== "string") return "";
  const first = address.split(",")[0].trim();
  return first.replace(/^\d+[\w-]*\s+/, "").trim();
};

/**
 * The listing-agent first touch. `salutation` comes from buildSalutation,
 * e.g. "Hi Lazaro," / "Hi there,".
 */
export const buildListingAgentBody = (opp) => {
  const street = streetName(opp?.project_address || opp?.name);
  const where = street ? `on ${street}, or any listing,` : "on any of your listings";
  return (
    "Ryan with The Shirtless Handyman. I do seamless microcement baths and Venetian plaster around New Orleans. " +
    `If a buyer ${where} wants the bath redone, I can quote it fast so it doesn't stall the deal. Happy to send photos.`
  );
};

/**
 * The follow-up "something to answer" line. Names the area of Ryan's most
 * recent finished shower only when he filled it in (Settings → "Where was
 * your last finished shower?"), so a draft never claims a job that didn't
 * happen.
 */
export const recentWorkLine = (area) => {
  const a = (area || "").trim();
  return a
    ? `Finished a seamless microcement shower in ${a} last week. Want me to send a couple photos or drop a sample board by?`
    : "I've been finishing seamless microcement showers around New Orleans. Want me to send a couple photos or drop a sample board by?";
};
