/**
 * Shared salutation helpers for every draft-builder in the app.
 *
 * Two bugs this module exists to prevent:
 *
 *   1. Business-name-as-first-name. If `decision_maker` is empty the
 *      draft builders were falling back to `opp.name.split(" ")[0]` —
 *      which pulls "Tristan" out of "Tristan Construction LLC", "MRB"
 *      out of "MRB Investments LLC", etc. The classifier NEVER writes
 *      a person's first name into the business-name field, so this
 *      always produced a fake first name.
 *
 *   2. Duplicate greeting. When the Airtable classifier populates
 *      `first_message` with its own "Hi X," line, the builder was still
 *      prepending its own "Hi X," — producing two greetings in every
 *      outgoing draft.
 *
 * Every draft/letter/message builder in the codebase now routes through
 * these helpers.
 */

// Tokens that make a name-string obviously a business. If ANY of these
// appears as a whole word the string is treated as a company and no
// personal first-name is extracted from it. Combines: legal-entity
// suffixes (LLC/Inc/…), organizational nouns (Group/Holdings/…), and
// contractor-adjacent service descriptors Ryan sees in his data
// (Living, Pros, Roofing, Kitchens, Pool, etc.).
const BUSINESS_TOKEN_RE =
  /\b(?:LLC|L\.L\.C\.?|LLP|LP|PC|PLLC|Inc|Inc\.?|Incorporated|Corp|Corp\.?|Corporation|Co\.?|Company|Companies|Ltd|Ltd\.?|Limited|Group|Holdings|Enterprises|Partners|Partnership|Properties|Property|Realty|Realtors|Homes|Home|Construction|Contracting|Contractors|Contractor|Builders|Builder|Building|Design|Designs|Interiors|Studio|Studios|Services|Solutions|Restoration|Remodeling|Renovation|Renovations|Development|Developments|Investments|Investment|Capital|Ventures|Rentals|Rental|Estates|Estate|Management|Consulting|Consultants|Associates|Bros|Brothers|Sons|Team|Trust|LTD|GP|Foundation|Living|Pros|Kitchens|Kitchen|Baths|Bath|Roofing|Roofs|Roof|Plumbing|Electric|Electrical|HVAC|Landscaping|Landscape|Painting|Painters|Painter|Cleaning|Handyman|Craft|Crafts|Works|Repair|Repairs|Trades|Pool|Pools|Fence|Fencing|Flooring|Floors|Tile|Tiles|Cabinets|Cabinetry|Countertops|Millwork|Art|Arts|Masonry|Concrete|Drywall|Framing|Windows|Doors|Gutters|Decks|Deck|Patio|Patios)\b/i;

// "&" or "and" between capitalized words usually indicates a multi-owner
// business (e.g. "Smith & Jones", "Miller and Associates").
const BUSINESS_CONJ_RE = /\s(?:&|and)\s/i;

/**
 * looksLikeBusiness — heuristic. True when the string looks like a
 * company/organization rather than a person.
 */
export const looksLikeBusiness = (name) => {
  if (!name || typeof name !== "string") return false;
  const s = name.trim();
  if (!s) return false;
  if (BUSINESS_TOKEN_RE.test(s)) return true;
  if (BUSINESS_CONJ_RE.test(s)) return true;
  return false;
};

/**
 * personalFirstName — extract a safe personal first name from a name
 * field. Returns null if the value is missing, empty, or looks like a
 * business. Strips surrounding punctuation and quotes.
 */
export const personalFirstName = (name) => {
  if (!name || typeof name !== "string") return null;
  const s = name.trim();
  if (!s) return null;
  if (looksLikeBusiness(s)) return null;
  const first = s.split(/\s+/)[0].replace(/[^\p{L}\p{N}'\-]/gu, "");
  return first || null;
};

/**
 * buildSalutation — the ONE source of truth for opening a message body.
 * Accepts an explicit ordered list of candidate name fields — callers
 * only pass fields that are supposed to hold a PERSON name
 * (`decision_maker`, `owner_name`, `agent_name`). The generic `name`
 * field on an Opportunity DTO is the record/project name (e.g.
 * "Backyard Living", "150 Zachary Taylor Dr") and MUST NOT be passed
 * here — it will otherwise produce "Hi Backyard,".
 *
 * Business-shaped candidates are skipped ("MRB Investments LLC" → skip)
 * and the next candidate is tried. When every candidate is empty or
 * business-shaped a neutral generic greeting is emitted
 * ("Hi there," / "Dear Property Owner,").
 *
 * @param {string|string[]} candidates — ordered list of name strings
 * @param {object} [opts]
 * @param {"Hi"|"Hey"|"Hello"|"Dear"} [opts.verb="Hi"]
 * @param {string} [opts.generic="there"]
 * @returns {string} e.g. "Hi John,"
 */
export const buildSalutation = (candidates, opts = {}) => {
  const verb = opts.verb || "Hi";
  const generic = opts.generic || "there";
  const list = Array.isArray(candidates) ? candidates : [candidates];
  for (const c of list) {
    const first = personalFirstName(c);
    if (first) return `${verb} ${first},`;
  }
  return `${verb} ${generic},`;
};

// Matches a single leading greeting line so we can strip it from a body
// the classifier already personalised. Handles: Hi / Hey / Hello / Dear /
// Good morning|afternoon|evening. Optional trailing comma/period/bang/colon.
// Consumes the trailing newline(s) too so the body reflows cleanly.
const LEADING_GREETING_RE =
  /^\s*(?:Hi|Hey|Hello|Dear|Good\s+(?:morning|afternoon|evening))\b[^\n]{0,80}[,.!:]?\s*(?:\n+|$)/i;

/**
 * stripLeadingGreeting — remove any greeting line the classifier already
 * added to the body, so the builder can prepend a single well-formed
 * greeting of its own. Idempotent; safe on empty / non-string input.
 */
export const stripLeadingGreeting = (body) => {
  if (!body || typeof body !== "string") return body || "";
  const trimmed = body.replace(LEADING_GREETING_RE, "");
  return trimmed.replace(/^\s+/, "");
};
