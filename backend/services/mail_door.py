"""Keep interior work. A missing name, phone, or email is not a pass.

The only intake pass is a lead that is not our lane. Our lane is interior
work: showers, baths, kitchens, microcement, Venetian plaster, and the
same kind of work. An exterior-only permit (roof, siding, fence, gutter)
is out of lane.

A missing owner name is not a pass, including an LLC-owned multi-family
with nobody's name on the permit. Those leads stay and go to enrichment.
An address with no phone and no email is still a mail / door-knock lead
(`mail-door`): a hanger, a postcard, or a knock. Dropping a lead because
no contact was found happens only after two enrichment attempts are on
the record and both failed. That decision lives with the attempt log;
this module only decides the lane.

Address-only leads never land in a call or text queue. A lead that came
from a permit or a sale record does not get a cold call or a cold text
unless someone has already said yes (SMS Permission, or they replied).

The mirror for the door-hanger page is `frontend/src/lib/mailDoor.js`.
Keep the two in sync.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from services.enrichment_attempts import should_drop_for_no_contact
from services.field_norm import clean_text, has_address, is_valid_email, is_valid_phone, resolved_email, resolved_phone

MAIL_DOOR = "mail-door"
NO_CONTACT_REASON = "no usable contact"

PASS_EXTERIOR = "pass-exterior"
# Historical label. disposition() does not return it: a missing name is not a pass.
PASS_LLC_MULTIFAMILY = "pass-llc-multifamily"
KEEP_MAIL_DOOR = "keep-mail-door"
KEEP = "keep"
SKIP = "skip"

PHONE_TEXT_MISSIONS = ("Call Today", "Send Text")

_BUSINESS = re.compile(
    r"\b(?:llc|l\.l\.c\.?|inc|incorporated|corp|corporation|company|ltd|limited|"
    r"holdings|enterprises|partners|partnership|properties|property|realty|"
    r"realtors|homes|construction|contracting|contractors|contractor|builders|"
    r"builder|restoration|investments|investment|capital|funding|ventures|"
    r"management|group|trust)\b",
    re.IGNORECASE,
)
_EXTERIOR = re.compile(
    r"\b(?:roof|roofing|siding|fence|fencing|gutter|gutters|driveway|awning|"
    r"demolition|solar)\b|\bexterior\s+paint\b|\bwindow\s+replacement\b|\bnew\s+windows\b",
    re.IGNORECASE,
)
_INTERIOR = re.compile(
    r"\b(?:shower|showers|bath|baths|bathroom|tub|tubs|kitchen|kitchens|"
    r"plaster|microcement|tadelakt|venetian|marmorino|countertops?|counters?|"
    r"floors?|flooring|cabinets?|cabinetry|drywall|interior|wetrooms?|"
    r"wet\s+rooms?|gut)\b",
    re.IGNORECASE,
)
_MULTIFAMILY = re.compile(
    r"\b(?:duplex|triplex|fourplex|four-plex|4-plex|multifamily|multi-family|"
    r"multi\s+family|apartments?|apt|plex|two-family|two\s+family|2-family|"
    r"four\s+family)\b",
    re.IGNORECASE,
)
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
_CONSENT = {"yes", "existing customer", "warm relationship"}
_PERSON_FIELDS = (
    "contact_name",
    "decision_maker",
    "owner",
    "applicant",
    "contractor",
    "contact_company",
    "company",
)
_SCOPE_FIELDS = (
    "project_type",
    "opportunity_type",
    "permit_description",
    "signal_found",
    "signal_type",
    "name",
)
_ADDRESS_KEYS = ("project_address", "address")


def _text(record: Dict[str, Any], *keys: str) -> str:
    parts = []
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return " ".join(parts)


def _soften(value: str) -> str:
    """Hyphens and underscores are word characters, so "tub-to-shower" and
    "bathroom_remodel" would hide the trade words from a word-boundary match."""
    return re.sub(r"[_-]+", " ", value)


def scope_text(record: Dict[str, Any]) -> str:
    return _soften(_text(record, *_SCOPE_FIELDS))


def looks_like_business(value: Any) -> bool:
    text = clean_text(value)
    return bool(text and _BUSINESS.search(text))


def _person_chunks(value: Any) -> List[str]:
    text = clean_text(value) or ""
    parts = re.split(r"\s*(?:,|;|&|\band\b)\s*", text, flags=re.IGNORECASE)
    return [part.strip() for part in parts if part and part.strip()]


def is_person_name(value: Any) -> bool:
    """True for "Edward Rafidi" or "Gerald Ludwig Stawski Jr.".

    A business ("CLS Properties 12 LLC", "Feelgood Construction Company")
    is not a person, and a single word is not enough.
    """
    for chunk in _person_chunks(value):
        if looks_like_business(chunk):
            continue
        words = re.findall(r"[A-Za-z][A-Za-z.'-]*", chunk)
        names = [word for word in words if word.lower().rstrip(".") not in _SUFFIXES and len(word) >= 2]
        if len(names) >= 2:
            return True
    return False


def has_named_person(record: Dict[str, Any]) -> bool:
    return any(is_person_name(record.get(key)) for key in _PERSON_FIELDS)


def is_exterior_only(record: Dict[str, Any]) -> bool:
    text = scope_text(record)
    if not text or not _EXTERIOR.search(text):
        return False
    return _INTERIOR.search(text) is None


def is_interior_job(record: Dict[str, Any]) -> bool:
    text = scope_text(record)
    return bool(text and _INTERIOR.search(text))


def is_multifamily(record: Dict[str, Any]) -> bool:
    blob = " ".join(
        _soften(part) for part in (scope_text(record), _text(record, *_ADDRESS_KEYS)) if part
    )
    return bool(blob and _MULTIFAMILY.search(blob))


def is_llc_owned(record: Dict[str, Any]) -> bool:
    """The owner of record is a company. A contractor name does not count."""
    owner = clean_text(record.get("owner"))
    if owner:
        return looks_like_business(owner)
    for key in ("contact_name", "company", "contact_company"):
        if looks_like_business(record.get(key)):
            return True
    return False


def has_property_address(record: Dict[str, Any]) -> bool:
    return has_address(record, _ADDRESS_KEYS)


def has_phone(record: Dict[str, Any]) -> bool:
    return is_valid_phone(resolved_phone(record))


def has_email(record: Dict[str, Any]) -> bool:
    return is_valid_email(resolved_email(record))


def is_permit_or_sale(record: Dict[str, Any]) -> bool:
    blob = _text(record, "source", "source_category").lower()
    return "permit" in blob or "sale" in blob


def has_phone_consent(record: Dict[str, Any]) -> bool:
    """Yes / an existing relationship / a reply. Unknown and blank are not consent."""
    for key in ("sms_permission", "contact_consent", "call_consent"):
        value = (clean_text(record.get(key)) or "").lower()
        if value in _CONSENT:
            return True
    status = _text(record, "outreach_status", "contact_state")
    if re.search(r"\b(replied|reply received)\b", status, re.IGNORECASE):
        return True
    return record.get("flag_reply_received") is True


def disposition(record: Dict[str, Any]) -> str:
    """What to do with this lead at intake. Does not write anything.

    Exterior-only permits are out of lane. Everything else interior stays,
    even with no owner name, phone, or email. An address and no phone or
    email is tagged for a door hanger. A missing name on an LLC-owned
    multi-family is not a pass.
    """
    if not record:
        return SKIP
    if is_exterior_only(record):
        return PASS_EXTERIOR
    if not is_interior_job(record):
        return SKIP
    if has_property_address(record) and not has_phone(record) and not has_email(record):
        return KEEP_MAIL_DOOR
    return KEEP


def phone_text_block_reason(record: Dict[str, Any]) -> Optional[str]:
    """Why this lead must not be called or texted, or None when a call is allowed."""
    if not has_phone(record):
        return "no-phone"
    if is_permit_or_sale(record) and not has_phone_consent(record):
        return "permit-or-sale-no-consent"
    return None


def guard_phone_text_mission(mission: str, record: Dict[str, Any]) -> str:
    """Call Today / Send Text are not legal queues for these leads."""
    if mission not in PHONE_TEXT_MISSIONS:
        return mission
    if not phone_text_block_reason(record):
        return mission
    if has_email(record):
        return "Send Email"
    if disposition(record) == KEEP_MAIL_DOOR:
        return "Visit Property"
    return "Research First"


def annotate_mail_door(opp: Dict[str, Any]) -> Dict[str, Any]:
    """Derived fields only. Does not write Airtable."""
    kind = disposition(opp)
    opp["mail_door"] = kind == KEEP_MAIL_DOOR
    if kind == KEEP_MAIL_DOOR:
        opp["contact_channel"] = MAIL_DOOR
    else:
        opp["contact_channel"] = opp.get("contact_channel") or opp.get("first_contact_channel")
    opp["phone_text_block"] = phone_text_block_reason(opp)
    opp["keep_disposition"] = kind
    return opp


def is_no_contact_pass(opp: Dict[str, Any]) -> bool:
    """Passed for missing contact, including the 2026-11-16 cleanup."""
    outcome = (clean_text(opp.get("outcome")) or "").lower()
    if outcome == NO_CONTACT_REASON:
        return True
    log = _text(opp, "activity_log_raw", "activity_log")
    return "no contact, stale" in log.lower()


def review_no_contact_passes(opps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Plan only. Nothing here writes, and nothing here calls a paid lookup."""
    restore: List[Dict[str, Any]] = []
    keep_passed: List[Dict[str, Any]] = []
    leave: List[Dict[str, Any]] = []
    for opp in opps or []:
        if not is_no_contact_pass(opp):
            continue
        kind = disposition(opp)
        row = {
            "id": opp.get("id"),
            "name": opp.get("name"),
            "address": clean_text(opp.get("project_address") or opp.get("address")),
            "disposition": kind,
        }
        if kind in (KEEP_MAIL_DOOR, KEEP) and not should_drop_for_no_contact(opp):
            row["updates"] = restore_updates(opp, kind)
            restore.append(row)
        elif kind in (KEEP_MAIL_DOOR, KEEP, PASS_EXTERIOR, PASS_LLC_MULTIFAMILY, SKIP):
            # Out of lane, or two enrichment attempts already failed.
            keep_passed.append(row)
        else:
            leave.append(row)
    return {
        "restore": restore,
        "keep_passed": keep_passed,
        "leave": leave,
        "restore_count": len(restore),
        "keep_passed_count": len(keep_passed),
        "leave_count": len(leave),
        "writes": False,
    }


def restore_updates(opp: Dict[str, Any], kind: str) -> Dict[str, Any]:
    """Fields to write when Ryan applies the plan. No new Airtable options."""
    updates: Dict[str, Any] = {"outcome": ""}
    if (opp.get("status") or "") == "Disqualified":
        updates["status"] = "Needs research"
    if kind == KEEP_MAIL_DOOR:
        notes = clean_text(opp.get("notes")) or ""
        if MAIL_DOOR not in notes.lower():
            line = "Contact channel: mail-door"
            updates["notes"] = f"{notes}\n\n{line}".strip() if notes else line
    return updates
