"""Pure helpers for contact research.

No network and no Airtable. The enrichment batch, the Find contact button,
and the "Who runs this?" save path all build their field updates here so
the rules stay in one place:

- A found person goes on Contact name (`decision_maker`) and, when the
  lead is a property owner, on Owner as well.
- Residential permit lookups are tagged `homeowner` vs `business` so the
  UI can show a Do Not Call check on homeowner numbers.
- A failed paid call is recorded once as "Research failed" and is not
  retried by this module.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from services.field_norm import (
    clean_text,
    contact_column_filled,
    format_phone,
    is_valid_email,
    is_valid_phone,
    normalize_email,
    resolved_email,
    resolved_phone,
)

# Enrichment status values. "Research failed" is not in the base select
# today; the write path uses Airtable typecast so the first failure can
# add it. The other three already exist.
STATUS_CONTACT_FOUND = "Contact found"
STATUS_NO_CONTACT = "No contact found"
STATUS_RESEARCH_FAILED = "Research failed"
STATUS_READY = "ready for research"

READINESS_CONTACT_READY = "Contact Ready"
READINESS_NEEDS_PUBLIC = "Needs Public Contact"
READINESS_NEEDS_PROOF = "Needs Proof"

_CLOSED = {
    "won",
    "lost",
    "disqualified",
    "do not contact",
    "do_not_contact",
    "dead",
}
_HELD_HUNT = {"rejected", "paused", "pass"}

_COMMERCIAL_TOKENS = (
    "commercial",
    "contractor",
    "property management",
    "portfolio",
    "retail",
    "office building",
    "restaurant",
    "coffee shop",
    "hotel",
)
_RESIDENTIAL_TOKENS = (
    "residential",
    "single-family",
    "single family",
    "residence",
    "duplex",
    "triplex",
    "fourplex",
    "bathroom",
    "shower",
    "kitchen",
    "home",
    "house",
)

_SOURCE_RE = re.compile(r"contact source:\s*(homeowner|business)\b", re.I)
_LABEL_RE_CACHE: Dict[str, re.Pattern] = {}

# Keys the Airtable writer understands. Anything else stays off the payload.
PERSISTED_KEYS = {
    "decision_maker",
    "owner",
    "owner_mailing_address",
    "phone",
    "email",
    "enrichment_status",
    "contact_readiness",
    "contact_confidence",
    "contact_verified_date",
    "source_url",
    "public_contact_evidence",
    "notes",
    "first_message",
    "first_contact_message",
    "first_contact_channel",
    "draft_outreach_body",
    "draft_outreach_subject",
    "draft_outreach_generated_at",
    "draft_recipe",
}


def _label_re(label: str) -> re.Pattern:
    pat = _LABEL_RE_CACHE.get(label)
    if pat is None:
        pat = re.compile(rf"^{re.escape(label)}:\s*(.+)$", re.I | re.M)
        _LABEL_RE_CACHE[label] = pat
    return pat


def parse_labeled_line(answer: str, label: str) -> Optional[str]:
    """Last `LABEL: value` line, or None when it is a not-found sentinel."""
    matches = _label_re(label).findall(answer or "")
    if not matches:
        return None
    return _person_or_text(matches[-1], max_len=200 if label.upper() == "MAILING" else 120)


def parse_decision_maker_name(answer: str) -> Optional[str]:
    """Name from the `DECISION_MAKER:` line the research prompt requires."""
    return parse_labeled_line(answer, "DECISION_MAKER") or parse_labeled_line(answer, "NAME")


def _person_or_text(value: Any, max_len: int = 120) -> Optional[str]:
    text = clean_text(value)
    if not text or len(text) > max_len:
        return None
    lowered = text.lower()
    if "http://" in lowered or "https://" in lowered or "{" in text:
        return None
    if len(text.split()) > 12:
        return None
    return text


def clean_http_url(value: Any) -> Optional[str]:
    text = clean_text(value)
    if not text:
        return None
    if not (text.startswith("http://") or text.startswith("https://")):
        return None
    if " " in text:
        return None
    return text[:500]


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _blob(opp: Dict[str, Any], keys) -> str:
    return " ".join(_norm(opp.get(k)) for k in keys)


def is_residential_permit(opp: Dict[str, Any]) -> bool:
    """A permit lead that looks like a home, not a business or a partner.

    Used to choose the assessor/homeowner lookup. Commercial and partner
    leads stay on the business contact finder.
    """
    source = _norm(opp.get("source"))
    category = _norm(opp.get("source_category"))
    has_permit = bool(clean_text(opp.get("permit_number"))) or "permit" in source or category == "permit"
    if not has_permit:
        return False
    if _norm(opp.get("lane")) == "partner":
        return False
    blob = _blob(opp, ("project_type", "permit_description", "name", "company"))
    if any(tok in blob for tok in _COMMERCIAL_TOKENS):
        return False
    if any(tok in blob for tok in _RESIDENTIAL_TOKENS):
        return True
    # A permit with an address and no company on file is the homeowner case
    # the assessor lookup is for.
    return not clean_text(opp.get("company"))


def _has_reachable(opp: Dict[str, Any]) -> bool:
    """Contact phone / Contact email count. Legacy columns count only as fallback."""
    return bool(
        is_valid_phone(resolved_phone(opp))
        or is_valid_email(resolved_email(opp))
    )


def _checked_on(opp: Dict[str, Any]) -> str:
    return str(opp.get("contact_verified_date") or "")[:10]


def checked_recently(opp: Dict[str, Any], today: str, recheck_days: int) -> bool:
    """True when this lead was researched inside the skip window.

    `today` and the stored date are `YYYY-MM-DD`. A missing date is not recent.
    """
    raw = _checked_on(opp)
    if not raw:
        return False
    try:
        checked = date.fromisoformat(raw)
        current = date.fromisoformat(today[:10])
    except ValueError:
        return False
    return (current - checked).days < max(0, recheck_days)


def checked_today(opp: Dict[str, Any], today: str) -> bool:
    return _checked_on(opp) == (today or "")[:10]


def _closed(opp: Dict[str, Any]) -> bool:
    for key in ("status", "status_raw", "outreach_status"):
        if _norm(opp.get(key)) in _CLOSED:
            return True
    return False


def enrichment_skip_reason(
    opp: Dict[str, Any],
    *,
    today: str,
    recheck_days: int,
    force: bool = False,
) -> Optional[str]:
    """Why a batch run should not spend a credit on this lead.

    `force=True` is the manual Find contact button: it still refuses a
    lead with nothing to look up, and it still runs when the lead was
    checked recently.
    """
    if not (clean_text(opp.get("project_address")) or clean_text(opp.get("name")) or clean_text(opp.get("company"))):
        return "nothing to research"
    if not force and _closed(opp):
        return "closed"
    hunt = _norm(opp.get("hunt_status"))
    if not force and hunt in _HELD_HUNT:
        return "paused"
    if not force and opp.get("duplicate_of"):
        return "duplicate"
    if force:
        return None
    enrich = _norm(opp.get("enrichment_status"))
    readiness = (opp.get("contact_readiness") or "").strip()
    eligible = enrich == STATUS_READY or readiness == READINESS_NEEDS_PUBLIC
    if not eligible:
        return "not eligible"
    if _has_reachable(opp):
        return "already has contact"
    if checked_recently(opp, today, recheck_days):
        return "checked recently"
    return None


def _confidence(value: Any, *, has_phone: bool, has_email: bool, has_name: bool) -> str:
    text = _norm(value)
    if text in {"high", "medium", "low"}:
        return text.capitalize()
    if has_phone and has_email:
        return "High"
    if has_phone or has_email:
        return "Medium"
    if has_name:
        return "Low"
    return "Low"


def _contact_source(value: Any, opp: Dict[str, Any]) -> str:
    text = _norm(value)
    if "homeowner" in text or text == "home":
        return "homeowner"
    if "business" in text or "company" in text or "llc" in text:
        return "business"
    return "homeowner" if is_residential_permit(opp) else "business"


def _looks_like_scam(text: Any) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    return lowered.startswith("flag:") or "scam pattern" in lowered


def _merge_evidence(existing: Any, source: str, url: Optional[str], context: Optional[str]) -> str:
    lines = [f"Contact source: {source}"]
    if url:
        lines.append(f"Source URL: {url}")
    if context:
        lines.append(context.strip()[:800])
    block = "\n".join(lines)
    prior = (existing or "").strip() if isinstance(existing, str) else ""
    if not prior:
        return block
    if _SOURCE_RE.search(prior):
        replaced = _SOURCE_RE.sub(f"Contact source: {source}", prior, count=1)
        if context and context.strip()[:80] not in replaced:
            return f"{replaced}\n\n{context.strip()[:800]}"
        return replaced
    return f"{block}\n\n{prior}"


def _append_note(existing: Any, line: str) -> str:
    prior = (existing or "").strip() if isinstance(existing, str) else ""
    return f"{prior}\n\n{line}" if prior else line


def _fill(updates: Dict[str, Any], opp: Dict[str, Any], key: str, value: Optional[str], force: bool) -> None:
    if not value:
        return
    # Phone and email writes land on Contact phone / Contact email. A legacy
    # Phone number / Email copied onto the display key must not look like
    # the Contact column is already filled.
    if force or not contact_column_filled(opp, key):
        updates[key] = value


def build_research_updates(
    opp: Dict[str, Any],
    parsed: Dict[str, Any],
    *,
    today: str,
    force: bool = False,
) -> Dict[str, Any]:
    """Field updates for one finished contact-finder result.

    Returns `updates` (snake_case Airtable keys) plus `became_contact_ready`
    so the caller can draft a first message without a second paid lookup.
    Existing phone, email, name, owner, mailing address, and source URL
    are left alone unless `force` is set (the manual button).
    """
    source = _contact_source(parsed.get("contact_source"), opp)
    name = _person_or_text(parsed.get("owner_name"))
    mailing = _person_or_text(parsed.get("mailing_address"), max_len=200)
    phone = format_phone(parsed.get("phone")) if is_valid_phone(parsed.get("phone")) else None
    email = normalize_email(parsed.get("email")) if is_valid_email(parsed.get("email")) else None
    url = clean_http_url(parsed.get("source_url"))
    context = clean_text(parsed.get("entity_context"))
    scam = _looks_like_scam(context)

    updates: Dict[str, Any] = {}
    _fill(updates, opp, "decision_maker", name, force)
    # Owner is the property-owner field. Fill it when it is empty, and
    # replace it on a manual re-run. A homeowner lookup and a business
    # lookup both identify an owner; neither one wipes a name Ryan
    # already stored unless he tapped Find contact again.
    _fill(updates, opp, "owner", name, force)
    _fill(updates, opp, "owner_mailing_address", mailing, force)

    if not scam:
        _fill(updates, opp, "phone", phone, force)
        _fill(updates, opp, "email", email, force)

    has_phone = bool(
        not scam and (updates.get("phone") or is_valid_phone(resolved_phone(opp)))
    )
    has_email = bool(
        not scam and (updates.get("email") or is_valid_email(resolved_email(opp)))
    )
    found = has_phone or has_email
    already_ready = (opp.get("contact_readiness") or "").strip() == READINESS_CONTACT_READY

    if scam:
        updates["enrichment_status"] = STATUS_NO_CONTACT
        updates["contact_readiness"] = READINESS_NEEDS_PROOF
    elif found:
        updates["enrichment_status"] = STATUS_CONTACT_FOUND
        updates["contact_readiness"] = READINESS_CONTACT_READY
    else:
        updates["enrichment_status"] = STATUS_NO_CONTACT
        updates["contact_readiness"] = READINESS_NEEDS_PUBLIC

    updates["contact_confidence"] = _confidence(
        parsed.get("confidence"),
        has_phone=has_phone,
        has_email=has_email,
        has_name=bool(name or clean_text(opp.get("decision_maker"))),
    )
    if url and not clean_text(opp.get("source_url")):
        updates["source_url"] = url
    updates["public_contact_evidence"] = _merge_evidence(
        opp.get("public_contact_evidence"), source, url, context
    )
    updates["contact_verified_date"] = today[:10]
    note = (
        f"Contact Finder ({today[:10]}): "
        f"{context or 'no public contact found.'} "
        f"Contact source: {source}."
    )
    updates["notes"] = _append_note(opp.get("notes"), note)

    return {
        "updates": {k: v for k, v in updates.items() if k in PERSISTED_KEYS},
        "became_contact_ready": bool(found and not already_ready and not scam),
        "contact_source": source,
        "outcome": "no_contact" if scam or not found else "contact_found",
    }


def build_failure_updates(opp: Dict[str, Any], reason: str, *, today: str) -> Dict[str, Any]:
    """One failed paid call. Status records the failure; nothing is retried."""
    safe_reason = (reason or "unknown error").strip().replace("\n", " ")[:400]
    note = (
        f"Contact Finder ({today[:10]}): research failed — {safe_reason} "
        "No contact was changed. Status set to Research failed. "
        "This was not retried. Tap Find contact to run it again yourself."
    )
    updates = {
        "enrichment_status": STATUS_RESEARCH_FAILED,
        "contact_verified_date": today[:10],
        "notes": _append_note(opp.get("notes"), note),
    }
    return {
        "updates": updates,
        "became_contact_ready": False,
        "contact_source": extract_contact_source(opp),
        "outcome": "failed",
    }


def build_name_updates(
    opp: Dict[str, Any],
    answer: str,
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """Contact name / owner / mailing address parsed out of a research answer.

    Phone and email stay out of this payload. The owner-contact panel still
    saves those when Ryan taps Save. "Who runs this?" only has a name.
    """
    name = parse_decision_maker_name(answer)
    mailing = parse_labeled_line(answer, "MAILING")
    updates: Dict[str, Any] = {}
    _fill(updates, opp, "decision_maker", name, force)
    if name and (is_residential_permit(opp) or not clean_text(opp.get("company"))):
        _fill(updates, opp, "owner", name, force or is_residential_permit(opp))
    _fill(updates, opp, "owner_mailing_address", mailing, force)
    return {k: v for k, v in updates.items() if k in PERSISTED_KEYS}


def extract_contact_source(opp: Dict[str, Any]) -> Optional[str]:
    for key in ("public_contact_evidence", "notes"):
        match = _SOURCE_RE.search(str(opp.get(key) or ""))
        if match:
            return match.group(1).lower()
    return None


def annotate_contact_flags(opp: Dict[str, Any]) -> Dict[str, Any]:
    """Add `contact_source` and `dnc_check_required` for the UI.

    The Do Not Call flag is a reminder on a homeowner phone. It does not
    dial, text, or block anything by itself.
    """
    source = extract_contact_source(opp)
    phone = resolved_phone(opp)
    opp["contact_source"] = source
    opp["dnc_check_required"] = bool(source == "homeowner" and phone)
    return opp


def has_draft(opp: Dict[str, Any]) -> bool:
    for key in ("draft_outreach_body", "first_message", "first_contact_message"):
        if clean_text(opp.get(key)):
            return True
    return False


def draft_field_updates(draft: str, subject: str, recipe_text: str, *, generated_at: str, channel: str) -> Dict[str, Any]:
    """Draft-only fields. Nothing here sends or schedules outreach."""
    return {
        "draft_outreach_body": draft,
        "draft_outreach_subject": subject,
        "draft_outreach_generated_at": generated_at,
        "draft_recipe": recipe_text,
        "first_message": draft,
        "first_contact_message": draft,
        "first_contact_channel": channel,
    }


def today_iso(now: Optional[datetime] = None) -> str:
    current = now or datetime.now(timezone.utc)
    return current.date().isoformat()
