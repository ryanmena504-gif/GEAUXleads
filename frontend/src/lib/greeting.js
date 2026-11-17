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
 * @param {string} [opts.email] — the address the draft goes to. A personal
 *   inbox that doesn't match the name (flora@ vs "Janet") → generic greeting.
 * @returns {string} e.g. "Hi John,"
 */
export const buildSalutation = (candidates, opts = {}) => {
  const verb = opts.verb || "Hi";
  const generic = opts.generic || "there";
  const list = Array.isArray(candidates) ? candidates : [candidates];
  for (const c of list) {
    const first = personalFirstName(c);
    if (first && nameMatchesEmail(c, opts.email)) return `${verb} ${first},`;
    if (first) break; // a person's name that doesn't fit the inbox — don't guess
  }
  return `${verb} ${generic},`;
};

// Shared inboxes that say nothing about who reads them. A name can't
// contradict these, so any person name is allowed with them.
const ROLE_MAILBOXES = new Set([
  "info", "office", "hello", "hi", "contact", "contactus", "admin", "sales",
  "team", "support", "mail", "email", "inquiries", "inquiry", "general",
  "design", "designer", "designs", "studio", "service", "services", "booking",
  "bookings", "ask", "help", "leasing", "rentals", "marketing", "projects",
  "estimates", "quotes", "quote", "home", "homes", "listings", "realestate",
  "office1", "frontdesk", "reception", "manager", "management", "owner",
  "build", "builder", "builders", "construction", "jobs", "work", "noreply",
]);

/**
 * nameMatchesEmail — false only when the email is a PERSONAL inbox
 * (e.g. flora@…) whose local part shares no part of the contact name
 * (e.g. "Janet"). Then the name most likely belongs to someone else and
 * the greeting falls back to "Hi there". (2026-11-16: the Decor by Flora
 * draft said "Hey Janet" to flora@decoratingden.com.)
 *
 * No email, role inboxes (info@, office@, design@…) and short initials
 * (jd@, jds@) never block the name.
 */
export const nameMatchesEmail = (name, email) => {
  if (!email || typeof email !== "string" || !email.includes("@")) return true;
  if (!name || typeof name !== "string") return true;
  const local = email.split("@")[0].toLowerCase();
  const letters = local.replace(/[^a-z]/g, "");
  if (letters.length <= 3) return true;
  const parts = local.split(/[._\-+0-9]+/).filter(Boolean);
  if (parts.some((p) => ROLE_MAILBOXES.has(p)) || ROLE_MAILBOXES.has(letters)) return true;
  const tokens = name
    .toLowerCase()
    .split(/[^\p{L}]+/u)
    .filter((t) => t.length >= 2);
  if (tokens.length === 0) return true;
  if (tokens.some((t) => letters.includes(t))) return true;
  // jsmith@ / johns@ style: first initial + last name, or first name + initial.
  const [first, ...rest] = tokens;
  const last = rest[rest.length - 1];
  if (last && (letters === first[0] + last || letters.startsWith(first[0] + last))) return true;
  return false;
};

// Matches a single leading greeting line so we can strip it from a body
// the classifier already personalised. Handles: Hi / Hey / Hello / Dear /
// Good morning|afternoon|evening. Optional trailing comma/period/bang/colon.
// Consumes the trailing newline(s) too so the body reflows cleanly.
const LEADING_GREETING_RE =
  /^\s*(?:Hi|Hey|Hello|Dear|Good\s+(?:morning|afternoon|evening))\b[^\n]{0,80}[,.!:]?\s*(?:\n+|$)/i;

// Inline greeting: "Hi Jeff — Ryan, ..." — the greeting and the first
// sentence share one line, so the line pattern below can't match (it needs
// a newline or end-of-string within 80 chars — and on a SHORT single-line
// body it would eat the whole sentence instead). Draft Outreach Body copy
// from the outreach writer is written this way, so without this the
// composer would prepend its own greeting and send a doubled "Hi Jeff,
// Hi Jeff — ...". Strip just the greeting token (verb + optional name +
// dash / comma / colon / bang), leaving the sentence intact. Runs BEFORE
// the line pattern: on a greeting line ("Hi Jeff,\n...") it strips the
// same text, so the line pattern then has nothing left to do.
const INLINE_GREETING_RE =
  /^\s*(?:Hi|Hey|Hello|Dear|Good\s+(?:morning|afternoon|evening))\b(?:\s+[^\n,;:!—–-]{1,40})?\s*(?:[—–-]|,|:|!)\s+/i;

/**
 * stripLeadingGreeting — remove any greeting line the classifier already
 * added to the body, so the builder can prepend a single well-formed
 * greeting of its own. Idempotent; safe on empty / non-string input.
 */
export const stripLeadingGreeting = (body) => {
  if (!body || typeof body !== "string") return body || "";
  const trimmed = body.replace(INLINE_GREETING_RE, "").replace(LEADING_GREETING_RE, "");
  return trimmed.replace(/^\s+/, "");
};
