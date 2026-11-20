/**
 * Mail / door-knock leads. Mirror of backend/services/mail_door.py.
 *
 * Interior work stays: showers, baths, kitchens, microcement, Venetian
 * plaster, and the same kind of work. A missing owner name, phone, or
 * email is not a pass — including an LLC-owned multi-family with no
 * person named. An address with no phone or email is tagged mail-door
 * and belongs on the door-hanger route. Exterior-only permits stay passes.
 *
 * Keep this file in sync with the Python module.
 */
import { hasContactChannel } from "./contact";

export const MAIL_DOOR = "mail-door";

const BUSINESS = /\b(?:llc|l\.l\.c\.?|inc|incorporated|corp|corporation|company|ltd|limited|holdings|enterprises|partners|partnership|properties|property|realty|realtors|homes|construction|contracting|contractors|contractor|builders|builder|restoration|investments|investment|capital|funding|ventures|management|group|trust)\b/i;
const EXTERIOR = /\b(?:roof|roofing|siding|fence|fencing|gutter|gutters|driveway|awning|demolition|solar)\b|\bexterior\s+paint\b|\bwindow\s+replacement\b|\bnew\s+windows\b/i;
const INTERIOR = /\b(?:shower|showers|bath|baths|bathroom|tub|tubs|kitchen|kitchens|plaster|microcement|tadelakt|venetian|marmorino|countertops?|counters?|floors?|flooring|cabinets?|cabinetry|drywall|interior|wetrooms?|wet\s+rooms?|gut)\b/i;
const MULTIFAMILY = /\b(?:duplex|triplex|fourplex|four-plex|4-plex|multifamily|multi-family|multi\s+family|apartments?|apt|plex|two-family|two\s+family|2-family|four\s+family)\b/i;
const SUFFIXES = new Set(["jr", "sr", "ii", "iii", "iv", "v"]);
const CONSENT = new Set(["yes", "existing customer", "warm relationship"]);
const PERSON_FIELDS = ["contact_name", "decision_maker", "owner", "applicant", "contractor", "contact_company", "company"];

const text = (value) => (value == null ? "" : String(value).trim());

const soften = (value) => text(value).replace(/[_-]+/g, " ");

const scopeText = (opp) =>
  soften(
    ["project_type", "opportunity_type", "permit_description", "signal_found", "signal_type", "name"]
      .map((key) => text(opp?.[key]))
      .filter(Boolean)
      .join(" "),
  );

export const looksLikeBusiness = (value) => BUSINESS.test(text(value));

const personChunks = (value) =>
  text(value)
    .split(/\s*(?:,|;|&|\band\b)\s*/i)
    .map((part) => part.trim())
    .filter(Boolean);

export const isPersonName = (value) =>
  personChunks(value).some((chunk) => {
    if (looksLikeBusiness(chunk)) return false;
    const names = (chunk.match(/[A-Za-z][A-Za-z.'-]*/g) || []).filter(
      (word) => !SUFFIXES.has(word.toLowerCase().replace(/\.$/, "")) && word.length >= 2,
    );
    return names.length >= 2;
  });

export const hasNamedPerson = (opp) => PERSON_FIELDS.some((key) => isPersonName(opp?.[key]));

export const isExteriorOnly = (opp) => {
  const scope = scopeText(opp);
  return Boolean(scope) && EXTERIOR.test(scope) && !INTERIOR.test(scope);
};

export const isInteriorJob = (opp) => INTERIOR.test(scopeText(opp));

const addressText = (opp) => text(opp?.project_address || opp?.address);

export const isMultifamily = (opp) => MULTIFAMILY.test(soften(`${scopeText(opp)} ${addressText(opp)}`));

export const isLlcOwned = (opp) => {
  const owner = text(opp?.owner);
  if (owner) return looksLikeBusiness(owner);
  return ["contact_name", "company", "contact_company"].some((key) => looksLikeBusiness(opp?.[key]));
};

export const hasPropertyAddress = (opp) => /\d/.test(addressText(opp)) && addressText(opp).length >= 6;

export const PASS_EXTERIOR = "pass-exterior";
export const PASS_LLC_MULTIFAMILY = "pass-llc-multifamily";
export const KEEP_MAIL_DOOR = "keep-mail-door";
export const KEEP = "keep";
export const SKIP = "skip";

export const disposition = (opp) => {
  if (!opp) return SKIP;
  if (isExteriorOnly(opp)) return PASS_EXTERIOR;
  if (!isInteriorJob(opp)) return SKIP;
  if (hasPropertyAddress(opp) && !hasContactChannel(opp)) return KEEP_MAIL_DOOR;
  return KEEP;
};

export const isMailDoorLead = (opp) =>
  disposition(opp) === KEEP_MAIL_DOOR || opp?.contact_channel === MAIL_DOOR;

export const isNoContactPass = (opp) => {
  const outcome = text(opp?.outcome).toLowerCase();
  if (outcome === "no usable contact") return true;
  const log = text(opp?.activity_log_raw || opp?.activity_log).toLowerCase();
  return log.includes("no contact, stale");
};

/** Exterior-only. A missing name is not a pass. */
export const staysPassed = (opp) => disposition(opp) === PASS_EXTERIOR;

const consentValue = (opp) => text(opp?.sms_permission || opp?.contact_consent || opp?.call_consent).toLowerCase();

export const hasPhoneConsent = (opp) => {
  if (CONSENT.has(consentValue(opp))) return true;
  const status = `${text(opp?.outreach_status)} ${text(opp?.contact_state)}`;
  if (/\b(replied|reply received)\b/i.test(status)) return true;
  return opp?.flag_reply_received === true;
};

const isPermitOrSale = (opp) => {
  const blob = `${text(opp?.source)} ${text(opp?.source_category)}`.toLowerCase();
  return blob.includes("permit") || blob.includes("sale");
};

const hasPhone = (opp) => hasContactChannel(opp) && Boolean(text(opp?.contact_phone || opp?.phone || opp?.phone_number || opp?.phone_alt));

/** Why a call or text is off limits, or null when it is allowed. */
export const phoneTextBlockReason = (opp) => {
  if (!hasPhone(opp)) return "no-phone";
  if (isPermitOrSale(opp) && !hasPhoneConsent(opp)) return "permit-or-sale-no-consent";
  return null;
};

const hasEmail = (opp) => text(opp?.contact_email || opp?.email || opp?.email_alt).includes("@");

/**
 * Call Today and Send Text never stick on an address-only lead, or on a
 * permit / sale lead that has not consented.
 */
export const phoneTextMission = (opp, mission) => {
  const current = mission || opp?.daily_mission;
  if (current !== "Call Today" && current !== "Send Text") return current;
  if (!phoneTextBlockReason(opp)) return current;
  if (hasEmail(opp)) return "Send Email";
  if (isMailDoorLead(opp)) return "Visit Property";
  return "Research First";
};
