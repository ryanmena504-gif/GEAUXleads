"""Server-side outreach eligibility policy.

Single source of truth for "may this lead be approved / sent outreach?". Every
write route that approves a lead or dispatches a message evaluates this module
first; the UI calls the same evaluation read-only so the button state and the
server decision can never disagree.

Two design rules:

1. **Live fields only.** Eligibility is computed from the record's current
   column values. The AI-authored prose columns (`Ai summary`,
   `Missing information`, `Risk flags`) are advisory — they are generated once
   at enrichment time and go stale as the record is edited, so they may raise a
   warning but never satisfy a requirement.
2. **Both DTO shapes.** `leads_service` and `airtable_service` project the same
   Airtable table under different key names. Requirements are declared against
   *logical* concepts and resolved through `FIELD_ALIASES`, so one policy serves
   both.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from services.field_norm import (
    as_list,
    clean_text,
    contains_token,
    coerce_number,
    first_present,
    format_phone,
    has_address,
    is_valid_email,
    is_valid_phone,
    normalize_email,
)

BLOCKER = "blocker"
WARNING = "warning"

# Logical concept -> candidate DTO keys, most authoritative first. Covers both
# the leads_service DTO and the airtable_service opportunity DTO.
FIELD_ALIASES: Dict[str, Tuple[str, ...]] = {
    "display_name": ("name", "business_name", "contact_company", "company"),
    "phone": ("contact_phone", "phone", "phone_number", "phone_alt"),
    "email": ("contact_email", "email", "email_alt"),
    "address": ("address", "project_address"),
    "city": ("city",),
    "counterparty_person": ("contact_name", "decision_maker", "applicant", "owner"),
    "counterparty_org": ("contact_company", "company", "business_name", "contractor"),
    "category": ("opportunity_type", "project_type", "source_category"),
    "score": ("lead_score",),
    "confidence": ("contact_confidence", "contact_confidence_raw"),
    "message": ("first_message",),
    "approval_status": ("approval_status",),
    "outreach_status": ("outreach_status",),
    "workflow_status": ("status", "status_raw"),
    "risk_flags": ("risk_flags",),
    "ai_missing_information": ("missing_information",),
    "sent_at": ("message_sent_date", "date_contacted"),
    "sent_flag": ("outreach_sent", "flag_outreach_sent"),
}

# Ordered worst -> best. Airtable's `contact confidence` select uses these
# words; unrecognised values are treated as "unknown" and warn rather than block.
CONFIDENCE_RANK: Dict[str, int] = {
    "none": 0, "very low": 1, "low": 1, "poor": 1,
    "medium": 2, "moderate": 2, "med": 2, "fair": 2,
    "high": 3, "strong": 3, "verified": 4, "confirmed": 4,
}

# Risk vocabulary that must stop an approval outright.
BLOCKING_RISK_TOKENS: Tuple[str, ...] = (
    "do not contact", "do-not-contact", "dnc", "opted out", "opt out",
    "unsubscribed", "litigation", "lawsuit", "attorney", "deceased",
    "bankrupt", "fraud", "scam", "spam complaint", "harassment",
    "wrong number", "disconnected", "invalid contact", "duplicate",
)

# Risk vocabulary worth restating in the confirmation dialog but not blocking.
ADVISORY_RISK_TOKENS: Tuple[str, ...] = (
    "unverified", "stale", "low confidence", "competitor", "price sensitive",
    "out of area", "renter", "permit expired",
)

STATUS_DNC_TOKENS: Tuple[str, ...] = ("do not contact", "do-not-contact", "dnc", "blocked")
STATUS_SENT_TOKENS: Tuple[str, ...] = ("sent", "contacted", "replied", "closed", "complete")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw in ("true", "1", "yes", "on"):
        return True
    if raw in ("false", "0", "no", "off"):
        return False
    return default


@dataclass(frozen=True)
class PolicyThresholds:
    """Operator-tunable gates. Read from env at request time, not import time,
    so `/admin/reload` picks up changes without a redeploy."""

    min_score: float = 50.0
    min_confidence: str = "medium"
    require_address: bool = True
    require_category: bool = True
    require_counterparty: bool = True
    block_on_risk: bool = True
    block_duplicates: bool = True
    block_already_sent: bool = True

    @classmethod
    def from_env(cls) -> "PolicyThresholds":
        return cls(
            min_score=_env_float("OUTREACH_MIN_SCORE", 50.0),
            min_confidence=(os.environ.get("OUTREACH_MIN_CONTACT_CONFIDENCE")
                            or "medium").strip().lower(),
            require_address=_env_bool("OUTREACH_REQUIRE_ADDRESS", True),
            require_category=_env_bool("OUTREACH_REQUIRE_CATEGORY", True),
            require_counterparty=_env_bool("OUTREACH_REQUIRE_COUNTERPARTY", True),
            block_on_risk=_env_bool("OUTREACH_BLOCK_ON_RISK", True),
            block_duplicates=_env_bool("OUTREACH_BLOCK_DUPLICATES", True),
            block_already_sent=_env_bool("OUTREACH_BLOCK_ALREADY_SENT", True),
        )

    @property
    def min_confidence_rank(self) -> int:
        return CONFIDENCE_RANK.get(self.min_confidence, 2)


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    message: str
    field: Optional[str] = None
    remediation: Optional[str] = None


@dataclass(frozen=True)
class Recipient:
    """What the operator is actually about to contact. Restated verbatim in the
    confirmation dialog so an approval can never be a blind click."""

    display_name: Optional[str] = None
    counterparty: Optional[str] = None
    channel: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    category: Optional[str] = None
    message_preview: Optional[str] = None


@dataclass
class EligibilityResult:
    lead_id: Optional[str]
    eligible: bool
    score: Optional[float]
    score_source: str
    findings: List[Finding] = field(default_factory=list)
    checks: List[Dict[str, Any]] = field(default_factory=list)
    recipient: Recipient = field(default_factory=Recipient)
    thresholds: Dict[str, Any] = field(default_factory=dict)

    @property
    def blockers(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == BLOCKER]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == WARNING]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lead_id": self.lead_id,
            "eligible": self.eligible,
            "score": self.score,
            "score_source": self.score_source,
            "blockers": [asdict(f) for f in self.blockers],
            "warnings": [asdict(f) for f in self.warnings],
            "checks": self.checks,
            "recipient": asdict(self.recipient),
            "thresholds": self.thresholds,
        }


def resolve(record: Dict[str, Any], concept: str) -> Optional[str]:
    """First non-blank value for a logical concept across both DTO shapes."""
    return first_present(record, FIELD_ALIASES.get(concept, ()))


def _raw(record: Dict[str, Any], concept: str) -> Any:
    for key in FIELD_ALIASES.get(concept, ()):
        value = record.get(key)
        if value not in (None, "", []):
            return value
    return None


def confidence_rank(value: Any) -> Optional[int]:
    """Rank a contact-confidence cell. None when unset or unrecognised."""
    text = clean_text(value)
    if text is None:
        return None
    lowered = text.lower()
    for label, rank in sorted(CONFIDENCE_RANK.items(), key=lambda kv: -len(kv[0])):
        if label in lowered:
            return rank
    numeric = coerce_number(text)
    if numeric is None:
        return None
    if numeric <= 3:
        return int(numeric)
    if numeric <= 10:
        return 3 if numeric >= 7 else 2 if numeric >= 4 else 1
    return 3 if numeric >= 70 else 2 if numeric >= 40 else 1


def readiness_score(record: Dict[str, Any]) -> Tuple[float, str]:
    """The score the threshold is applied to, and where it came from.

    Prefers Airtable's own `Lead score` when the automation has populated it.
    That column is 0 for most rows in the live base, so we fall back to a
    score computed from the fields that actually make a lead contactable — the
    same inputs the blocker checks read, which keeps the number honest rather
    than inherited from stale enrichment prose.
    """
    explicit = coerce_number(_raw(record, "score"))
    if explicit is not None and explicit > 0:
        return float(explicit), "airtable_lead_score"

    score = 0.0
    if is_valid_phone(_raw(record, "phone")):
        score += 25
    if is_valid_email(_raw(record, "email")):
        score += 20
    if resolve(record, "counterparty_person"):
        score += 15
    elif resolve(record, "counterparty_org"):
        score += 10
    if has_address(record, FIELD_ALIASES["address"]):
        score += 15
    if resolve(record, "category"):
        score += 10
    rank = confidence_rank(_raw(record, "confidence"))
    if rank is not None:
        score += {0: 0, 1: 2, 2: 6, 3: 10, 4: 12}.get(rank, 0)
    if coerce_number(record.get("estimated_job_value") or record.get("estimated_value")):
        score += 5
    if record.get("qualified_opportunity") or record.get("flag_qualified"):
        score += 5
    if record.get("verified_opportunity") or record.get("flag_verified"):
        score += 5
    return min(score, 100.0), "computed_from_live_fields"


def _risk_findings(record: Dict[str, Any], thresholds: PolicyThresholds) -> List[Finding]:
    findings: List[Finding] = []
    flags = as_list(_raw(record, "risk_flags"))
    for flag in flags:
        text = clean_text(flag)
        if not text:
            continue
        lowered = text.lower()
        if any(token in lowered for token in BLOCKING_RISK_TOKENS):
            findings.append(Finding(
                code="blocking_risk_flag",
                severity=BLOCKER if thresholds.block_on_risk else WARNING,
                field="Risk flags",
                message=f"Blocking risk flag on the record: “{text}”.",
                remediation="Clear the risk flag in Airtable once resolved, or mark the lead Do Not Contact.",
            ))
        elif any(token in lowered for token in ADVISORY_RISK_TOKENS):
            findings.append(Finding(
                code="advisory_risk_flag",
                severity=WARNING,
                field="Risk flags",
                message=f"Advisory risk flag: “{text}”.",
            ))
    return findings


def evaluate(
    record: Dict[str, Any],
    thresholds: Optional[PolicyThresholds] = None,
    duplicate_of: Optional[str] = None,
) -> EligibilityResult:
    """Evaluate a lead/opportunity record against the outreach policy.

    `duplicate_of` is supplied by the dedupe layer: a non-canonical member of a
    duplicate group is never independently actionable.
    """
    thresholds = thresholds or PolicyThresholds.from_env()
    findings: List[Finding] = []
    checks: List[Dict[str, Any]] = []

    def check(code: str, label: str, passed: bool, detail: Optional[str] = None) -> bool:
        checks.append({"code": code, "label": label, "passed": passed, "detail": detail})
        return passed

    phone_raw = _raw(record, "phone")
    email_raw = _raw(record, "email")
    phone_ok = is_valid_phone(phone_raw)
    email_ok = is_valid_email(email_raw)

    # ---- 1. reachable contact ----
    if not check("verified_contact", "Verified phone or email", phone_ok or email_ok,
                 "phone" if phone_ok else "email" if email_ok else None):
        if phone_raw or email_raw:
            detail = []
            if phone_raw and not phone_ok:
                detail.append(f"phone “{clean_text(phone_raw)}” is not a dialable 10-digit number")
            if email_raw and not email_ok:
                detail.append(f"email “{clean_text(email_raw)}” is not a deliverable address")
            message = "No verified contact method — " + "; ".join(detail) + "."
        else:
            message = "No phone number or email address on the record."
        findings.append(Finding(
            code="no_verified_contact",
            severity=BLOCKER,
            field="Contact phone / Contact email",
            message=message,
            remediation="Run enrichment or add a verified phone/email in Airtable before approving.",
        ))

    # ---- 2. location ----
    address_ok = has_address(record, FIELD_ALIASES["address"])
    if thresholds.require_address:
        if not check("address", "Property or permit address", address_ok):
            findings.append(Finding(
                code="no_address",
                severity=BLOCKER,
                field="Address",
                message=("Only a city is recorded, no street address."
                         if resolve(record, "city") else "No property or permit address on the record."),
                remediation="Add the street address (or permit address) so outreach references a real property.",
            ))
    else:
        check("address", "Property or permit address (not enforced)", address_ok)

    # ---- 3. identified counterparty ----
    # The live Leads table has no Applicant/Contractor/Owner columns, so the
    # decision maker is `Contact name`; a named business (`Contact company` /
    # `Business name`) is accepted as the organizational equivalent.
    person = resolve(record, "counterparty_person")
    org = resolve(record, "counterparty_org")
    if thresholds.require_counterparty:
        if not check("counterparty", "Identified decision maker or business",
                     bool(person or org), person or org):
            findings.append(Finding(
                code="no_counterparty",
                severity=BLOCKER,
                field="Contact name / Contact company",
                message="No decision maker, owner, or business identified for this lead.",
                remediation="Populate Contact name (preferred) or Contact company before approving.",
            ))
        elif not person:
            findings.append(Finding(
                code="org_only_counterparty",
                severity=WARNING,
                field="Contact name",
                message=f"Addressed to the business “{org}” — no named individual on the record.",
            ))
    else:
        check("counterparty", "Identified decision maker (not enforced)", bool(person or org))

    # ---- 4. project / service category ----
    category = resolve(record, "category")
    if thresholds.require_category:
        if not check("category", "Project or service category", bool(category), category):
            findings.append(Finding(
                code="no_category",
                severity=BLOCKER,
                field="Opportunity type",
                message="No project or service category — the pitch cannot be targeted.",
                remediation="Set Opportunity type in Airtable (or map it from the Make scenario).",
            ))
    else:
        check("category", "Project or service category (not enforced)", bool(category))

    # ---- 5. score threshold ----
    score, score_source = readiness_score(record)
    if not check("score_threshold",
                 f"Score ≥ {thresholds.min_score:g}",
                 score >= thresholds.min_score,
                 f"{score:g} ({score_source})"):
        findings.append(Finding(
            code="score_below_threshold",
            severity=BLOCKER,
            field="Lead score",
            message=(f"Score {score:g} is below the approval threshold of "
                     f"{thresholds.min_score:g} (source: {score_source})."),
            remediation="Enrich the lead or lower OUTREACH_MIN_SCORE if the threshold is wrong for this base.",
        ))

    # ---- 6. contact confidence threshold ----
    rank = confidence_rank(_raw(record, "confidence"))
    if rank is None:
        check("confidence_threshold", f"Contact confidence ≥ {thresholds.min_confidence}",
              True, "not recorded")
        findings.append(Finding(
            code="confidence_unknown",
            severity=WARNING,
            field="contact confidence",
            message="Contact confidence is not recorded — reachability is unverified.",
        ))
    elif not check("confidence_threshold",
                   f"Contact confidence ≥ {thresholds.min_confidence}",
                   rank >= thresholds.min_confidence_rank,
                   clean_text(_raw(record, "confidence"))):
        findings.append(Finding(
            code="confidence_below_threshold",
            severity=BLOCKER,
            field="contact confidence",
            message=(f"Contact confidence “{clean_text(_raw(record, 'confidence'))}” is below the "
                     f"required minimum of “{thresholds.min_confidence}”."),
            remediation="Re-verify the contact, or lower OUTREACH_MIN_CONTACT_CONFIDENCE.",
        ))

    # ---- 7. risk ----
    risk_findings = _risk_findings(record, thresholds)
    findings.extend(risk_findings)
    check("no_blocking_risk", "No blocking risk flag",
          not any(f.severity == BLOCKER for f in risk_findings))

    for concept, label in (("workflow_status", "Status"),
                           ("approval_status", "Approval status"),
                           ("outreach_status", "Outreach status")):
        if contains_token(_raw(record, concept), STATUS_DNC_TOKENS):
            findings.append(Finding(
                code="marked_do_not_contact",
                severity=BLOCKER,
                field=label,
                message=f"{label} is set to Do Not Contact.",
                remediation="Clear the Do Not Contact state in Airtable before approving.",
            ))

    # ---- 8. duplicate suppression ----
    is_duplicate = bool(duplicate_of)
    if not check("canonical_record", "Not a suppressed duplicate", not is_duplicate, duplicate_of):
        findings.append(Finding(
            code="duplicate_lead",
            severity=BLOCKER if thresholds.block_duplicates else WARNING,
            field="Duplicate group",
            message=(f"This record duplicates lead {duplicate_of}, which is the canonical "
                     "record for this property/contact. Act on that one instead."),
            remediation="Approve the canonical lead, or resolve the duplicate in Airtable.",
        ))

    # ---- 9. already contacted ----
    already_sent = bool(
        _raw(record, "sent_at")
        or _raw(record, "sent_flag") is True
        or contains_token(_raw(record, "outreach_status"), STATUS_SENT_TOKENS)
    )
    if not check("not_already_sent", "Outreach not already sent", not already_sent):
        findings.append(Finding(
            code="already_contacted",
            severity=BLOCKER if thresholds.block_already_sent else WARNING,
            field="Outreach status / Message sent date",
            message="Outreach has already been sent to this lead — approving again risks a duplicate message.",
            remediation="Use follow-up rather than a fresh approval.",
        ))

    # ---- 10. advisory: stale AI prose ----
    ai_missing = [clean_text(m) for m in as_list(_raw(record, "ai_missing_information"))]
    ai_missing = [m for m in ai_missing if m]
    if ai_missing:
        findings.append(Finding(
            code="ai_missing_information",
            severity=WARNING,
            field="Missing information",
            message=("AI enrichment noted missing information (advisory, may be stale): "
                     + "; ".join(ai_missing[:5]) + "."),
        ))

    message = clean_text(_raw(record, "message"))
    if not message:
        findings.append(Finding(
            code="no_draft_message",
            severity=WARNING,
            field="First message",
            message="No draft outbound message has been composed yet.",
        ))

    channel = "phone" if phone_ok else "email" if email_ok else None
    recipient = Recipient(
        display_name=resolve(record, "display_name"),
        counterparty=person or org,
        channel=channel,
        phone=format_phone(phone_raw) if phone_ok else None,
        email=normalize_email(email_raw) if email_ok else None,
        address=resolve(record, "address"),
        category=category,
        message_preview=(message[:280] if message else None),
    )

    eligible = not any(f.severity == BLOCKER for f in findings)
    return EligibilityResult(
        lead_id=record.get("id"),
        eligible=eligible,
        score=score,
        score_source=score_source,
        findings=findings,
        checks=checks,
        recipient=recipient,
        thresholds={
            "min_score": thresholds.min_score,
            "min_contact_confidence": thresholds.min_confidence,
            "require_address": thresholds.require_address,
            "require_category": thresholds.require_category,
            "require_counterparty": thresholds.require_counterparty,
            "block_on_risk": thresholds.block_on_risk,
            "block_duplicates": thresholds.block_duplicates,
            "block_already_sent": thresholds.block_already_sent,
        },
    )


def computed_readiness(record: Dict[str, Any],
                       duplicate_of: Optional[str] = None) -> Dict[str, Any]:
    """Live-field readiness summary for the detail UI.

    Replaces the habit of rendering the AI's `Missing information` /
    `Risk flags` prose as if it described the record's current state. The AI
    text is still returned, explicitly namespaced as advisory.
    """
    result = evaluate(record, duplicate_of=duplicate_of)
    return {
        "eligible": result.eligible,
        "score": result.score,
        "score_source": result.score_source,
        "missing_fields": [
            {"field": f.field, "code": f.code, "message": f.message}
            for f in result.blockers
        ],
        "warnings": [
            {"field": f.field, "code": f.code, "message": f.message}
            for f in result.warnings
        ],
        "checks": result.checks,
        "advisory_ai_missing_information": [
            m for m in (clean_text(x) for x in as_list(_raw(record, "ai_missing_information"))) if m
        ],
        "advisory_ai_risk_flags": [
            m for m in (clean_text(x) for x in as_list(_raw(record, "risk_flags"))) if m
        ],
    }
