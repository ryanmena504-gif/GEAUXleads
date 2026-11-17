/**
 * Door-hanger route (2026-11-16 review).
 *
 * Open permit leads with an address but no phone or email can't be called
 * or emailed, but a door hanger only needs an address. This builds the
 * weekly walking list: grouped by ZIP (with the usual neighborhood name),
 * streets together, house numbers in order.
 */
import { hasContactChannel } from "./contact";

const CLOSED = new Set(["Won", "Lost", "Disqualified"]);

// Usual neighborhood names for the ZIPs Ryan works. Labels only — a lead's
// group is always its ZIP.
export const ZIP_NEIGHBORHOODS = {
  "70112": "Tremé / Tulane-Gravier",
  "70113": "Central City / Lower Garden District",
  "70114": "Algiers",
  "70115": "Uptown / Garden District",
  "70116": "French Quarter / Marigny / Tremé",
  "70117": "Bywater / St. Claude / Lower 9th",
  "70118": "Uptown / Carrollton",
  "70119": "Mid-City / Bayou St. John",
  "70121": "Old Jefferson",
  "70122": "Gentilly",
  "70123": "Harahan / River Ridge",
  "70124": "Lakeview",
  "70125": "Broadmoor / Freret",
  "70126": "Gentilly East / Pines Village",
  "70127": "New Orleans East",
  "70128": "New Orleans East",
  "70129": "New Orleans East / Venetian Isles",
  "70130": "CBD / Warehouse District / Irish Channel",
  "70131": "Algiers / Lower Coast",
  "70001": "Metairie",
  "70002": "Metairie",
  "70003": "Metairie",
  "70005": "Old Metairie",
  "70006": "Metairie",
  "70056": "Gretna",
  "70058": "Harvey",
  "70062": "Kenner",
  "70065": "Kenner",
  "70072": "Marrero",
};

const NO_ZIP = "No ZIP on the permit";

/** Source is a permit ("Permit" or "Permit Issued"). */
export const isPermitSource = (opp) => /^permit\b/i.test(String(opp?.source || "").trim());

export const addressOf = (opp) => String(opp?.project_address || "").trim();

/** Open permit lead with an address and no phone or email. */
export const isDoorHangerLead = (opp) =>
  Boolean(opp) &&
  !CLOSED.has(opp.status) &&
  isPermitSource(opp) &&
  Boolean(addressOf(opp)) &&
  !hasContactChannel(opp);

export const zipOf = (address) => {
  const m = String(address || "").match(/\b(70\d{3})(?:-\d{4})?\b/);
  return m ? m[1] : null;
};

/** "3219 Joseph St, New Orleans" → { number: 3219, street: "joseph st" } */
const streetKey = (address) => {
  const first = String(address || "").split(",")[0].trim();
  const m = first.match(/^(\d+)[\w-]*\s+(.*)$/);
  return m
    ? { number: Number(m[1]), street: m[2].toLowerCase() }
    : { number: Number.MAX_SAFE_INTEGER, street: first.toLowerCase() };
};

/**
 * buildDoorHangerRoute — [{ zip, label, stops: [opp…] }], biggest group
 * first, each group's stops ordered by street then house number. One stop
 * per address: duplicate records for the same door are folded together.
 */
export const buildDoorHangerRoute = (items) => {
  const seen = new Set();
  const groups = new Map();
  for (const opp of items || []) {
    if (!isDoorHangerLead(opp)) continue;
    const addr = addressOf(opp);
    const dedupeKey = addr.split(",")[0].trim().toLowerCase().replace(/\s+/g, " ");
    if (seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);
    const zip = zipOf(addr) || NO_ZIP;
    if (!groups.has(zip)) groups.set(zip, []);
    groups.get(zip).push(opp);
  }
  const out = [];
  for (const [zip, stops] of groups) {
    stops.sort((a, b) => {
      const ka = streetKey(addressOf(a));
      const kb = streetKey(addressOf(b));
      return ka.street.localeCompare(kb.street) || ka.number - kb.number;
    });
    const label = zip === NO_ZIP ? NO_ZIP : [zip, ZIP_NEIGHBORHOODS[zip]].filter(Boolean).join(" · ");
    out.push({ zip, label, stops });
  }
  out.sort((a, b) => {
    if (a.zip === NO_ZIP) return 1;
    if (b.zip === NO_ZIP) return -1;
    return b.stops.length - a.stops.length || a.zip.localeCompare(b.zip);
  });
  return out;
};
