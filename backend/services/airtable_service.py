"""
Live Airtable-backed opportunity service.

Design principles:
- Schema is fetched from Airtable at init using `schema.bases:read` — no field is
  guessed. The `KNOWN_FIELD_MAP` (Airtable field name -> internal snake_case key)
  is filtered against the base's real schema and only surviving mappings are used.
- Writes are strictly whitelisted (`EDITABLE_FIELDS`). Formula/rollup/lookup
  fields are automatically excluded even if listed.
- Activity timeline is synthesised from the record's real timestamps
  (`created_time`, `permit_filing_date`, and current `status`). No fabricated
  history. A dedicated interactions table can be plugged in later without
  changing the read contract.
- A tiny TTL cache keeps the dashboard fast and stays under Airtable's ~5 rps
  per-base rate limit.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pyairtable import Api

log = logging.getLogger("bloodhound.airtable")


class AirtableWriteError(Exception):
    """Raised when Airtable rejects a write. Carries the HTTP status code from
    the upstream response so the API layer can pass it through unchanged."""

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


# =============================================================================
# CENTRAL FIELD MAP — projects the LIVE `Leads` Airtable table into the
# dashboard's Opportunity DTO. The dashboard was originally built for an
# "Opportunities" table which no longer exists in this base (Perplexity's
# Make.com scenario rebuild dropped it). Instead of asking Ryan to recreate a
# duplicate table, we adapt the read layer to the source of truth: Leads.
#
# Rule: never rename, delete, or recreate Airtable fields; only map.
# Airtable field name (exact, case-sensitive) -> internal snake_case key.
# =============================================================================
LIVE_FIELDS: Dict[str, str] = {
    # Identity + timestamps
    "ID": "opportunity_id",
    "Leads Name": "name",
    "Created time": "created_time",
    "Contact data updated": "last_reviewed",
    "Action trigger time": "action_trigger_time",
    "Validated at": "validated_at",
    "Message generated at": "message_generated_at",

    # Signal / property
    "Source": "source",
    "Source URL": "source_url",
    "Source category": "source_category",
    "Signal found": "signal_type",
    "Address": "project_address",
    "City": "city",
    "Opportunity type": "project_type",
    "Permit number": "permit_number",
    "Permit description": "permit_description",
    "Estimated job value": "estimated_value",

    # Contact block
    "Contact name": "decision_maker",
    "Contact phone": "phone",
    "Contact email": "email",
    "Contact company": "company",
    "Contact website": "website",
    "Contact instagram": "instagram",
    "Contact facebook": "facebook",
    "Phone number": "phone_alt",
    "Email": "email_alt",
    "Website": "website_alt",
    "Instagram": "instagram_alt",
    "contact confidence": "contact_confidence_raw",
    "Best contact method": "best_contact_method",
    "Preferred contact method": "preferred_contact_method",
    "First message": "first_message",
    "First contact message": "first_contact_message",
    "First contact channel": "first_contact_channel",
    "Open approved message iPhone": "open_approved_message_iphone",
    "Open approved message": "open_approved_message",
    "SMS Permission": "sms_permission",

    # AI intelligence
    "Ai status": "ai_status",
    "Ai summary": "evidence_summary",
    "Why lead matters": "recommendation_reason",
    "Missing information": "missing_information",
    "Risk flags": "risk_flags",
    "Next action": "next_best_action",
    "recommended action": "recommended_action",
    "Recommended offer": "recommended_offer",
    "Outreach angle": "outreach_angle",
    "Confidence score": "confidence_score",
    "Lead score": "lead_score",
    "Priority": "priority_raw",
    "Revenue potential": "revenue_potential",

    # Workflow state
    "Status": "status_raw",
    "Approval status": "approval_status",
    "Outreach status": "outreach_status",
    "Hunt status": "hunt_status",
    "Enrichment status": "enrichment_status",
    "Reply summary": "reply_summary",
    "Reply classification": "reply_classification",
    "Rejection reason": "outcome",
    "Notes": "notes",
    "Outreach channel": "outreach_channel",

    # Dates
    "Next followup": "next_follow_up",
    "Date contacted": "date_contacted",
    "Date replied": "date_replied",
    "Message sent date": "message_sent_date",

    # Signal / property flags (checkboxes from the automation)
    "Local service area": "flag_local_service",
    "Bathroom or renovation signal": "flag_bathroom_signal",
    "Premium property or client ": "flag_premium",
    "Recent activity ": "flag_recent_activity",
    "Partnership potential ": "flag_partnership",

    # Funnel checkboxes (drive derived Status)
    "Verified opportunity": "flag_verified",
    "Qualified opportunity": "flag_qualified",
    "Outreach sent": "flag_outreach_sent",
    "Reply received": "flag_reply_received",
    "Positive conversation": "flag_positive_conversation",
    "Estimate opportunity": "flag_estimate",
    "Job won": "flag_won",

    # Money
    "Closed revenue": "closed_revenue",
    "Estimated gross profit": "estimated_gross_profit",
}

# Fields the app talks about but which are NOT on the Leads table.
# They render as "Not available yet" — we never invent values or create fields.
PENDING_FIELDS: Dict[str, str] = {
    "Applicant": "applicant",
    "Contractor": "contractor",
    "Owner": "owner",
    "Permit filing date": "permit_filing_date",
}

KNOWN_FIELD_MAP: Dict[str, str] = {**LIVE_FIELDS, **PENDING_FIELDS}

# Fields we will read but NEVER write. These are formulas, auto-numbers, or
# system-managed timestamps. Enforced in addition to the schema's own type check.
EXPLICIT_READONLY: set = {
    "ID",
    "Leads Name",
    "Created time",
    "Contact data updated",
    "Action trigger time",
    "Validated at",
    "Message generated at",
    "Ai status",
    "Ai summary",
    "Why lead matters",
    "Missing information",
    "Risk flags",
    "Next action",
    "recommended action",
    "Recommended offer",
    "Outreach angle",
    "First message",
    "Confidence score",
    "Lead score",
    "Enrichment status",
    "Verified opportunity",
    "Qualified opportunity",
    "Closed revenue",
    "Estimated gross profit",
    "SMS Permission",
}

# Only these Airtable field names may ever be written from the app.
# The dashboard's Decision Panel sends: status, ryans_decision,
# next_follow_up, outcome. We project those onto Leads columns:
#   status         -> Status
#   ryans_decision -> Hunt status
#   next_follow_up -> Next followup
#   outcome        -> Rejection reason
EDITABLE_FIELDS = {
    "Status",
    "Hunt status",
    "Next followup",
    "Rejection reason",
    "Notes",
    "Approval status",
    "Outreach status",
    "Outreach channel",
    "Message sent date",
    "Date contacted",
    "Reply classification",
    "Reply summary",
    "Date replied",
}

# Snake_case aliases the frontend/API layer speaks -> Airtable field name.
# Overrides the reverse of KNOWN_FIELD_MAP where UI wording differs from the
# Airtable column name.
WRITE_ALIAS: Dict[str, str] = {
    "status": "Status",
    "ryans_decision": "Hunt status",
    "next_follow_up": "Next followup",
    "outcome": "Rejection reason",
    "notes": "Notes",
    "approval_status": "Approval status",
    "outreach_status": "Outreach status",
    "outreach_channel": "Outreach channel",
    "message_sent_date": "Message sent date",
    "date_contacted": "Date contacted",
    "reply_classification": "Reply classification",
    "reply_summary": "Reply summary",
    "date_replied": "Date replied",
}

# Airtable field types that are ALWAYS read-only regardless of allowlist.
READONLY_FIELD_TYPES = {
    "formula",
    "rollup",
    "count",
    "lookup",
    "createdTime",
    "createdBy",
    "lastModifiedTime",
    "lastModifiedBy",
    "autoNumber",
    "button",
    "externalSyncSource",
}

# Statuses considered "closed" for pipeline/summary calcs.
CLOSED_STATUSES = {"Won", "Lost", "Disqualified"}


# ---------------------------------------------------------------------------
# Canonical sort — `Lead score` (Airtable) is the primary priority everywhere.
# Unscored records rank BELOW scored ones. Ties: freshness DESC, id ASC.
# ---------------------------------------------------------------------------
def _score_num(o: Dict[str, Any]) -> Optional[float]:
    s = o.get("priority_score")
    return s if isinstance(s, (int, float)) else None


def _date_str(o: Dict[str, Any]) -> str:
    return (o.get("last_reviewed") or o.get("created_time") or "")


def _conf_num(o: Dict[str, Any]) -> Optional[float]:
    c = o.get("confidence_score") or o.get("evidence_confidence")
    try:
        return float(c) if c not in (None, "") else None
    except (TypeError, ValueError):
        return None


def sort_opportunities(items: List[Dict[str, Any]], mode: str = "lead_score") -> List[Dict[str, Any]]:
    """Canonical dashboard sort. Never mutates the input list."""
    mode = (mode or "lead_score").lower()
    if mode == "freshness":
        with_d = [o for o in items if _date_str(o)]
        without = [o for o in items if not _date_str(o)]
        with_d.sort(key=lambda o: o.get("id") or "")
        with_d.sort(key=lambda o: _date_str(o), reverse=True)
        without.sort(key=lambda o: o.get("id") or "")
        return with_d + without
    if mode == "confidence":
        scored = [o for o in items if _conf_num(o) is not None]
        unscored = [o for o in items if _conf_num(o) is None]
        scored.sort(key=lambda o: o.get("id") or "")
        scored.sort(key=lambda o: _date_str(o), reverse=True)
        scored.sort(key=lambda o: -_conf_num(o))
        unscored.sort(key=lambda o: o.get("id") or "")
        return scored + unscored
    # Default: canonical Lead score
    scored = [o for o in items if _score_num(o) is not None]
    unscored = [o for o in items if _score_num(o) is None]
    scored.sort(key=lambda o: o.get("id") or "")
    scored.sort(key=lambda o: _date_str(o), reverse=True)
    scored.sort(key=lambda o: -_score_num(o))
    unscored.sort(key=lambda o: o.get("id") or "")
    return scored + unscored


PIPELINE_STATUSES = [
    "New",
    "Needs research",
    "Ready",
    "Conversation started",
    "Estimate requested",
    "Estimate sent",
    "Won",
    "Lost",
    "Disqualified",
]

# Derive a dashboard-pipeline stage from the Leads workflow state.
# IMPORTANT: `outreach_status` is Ryan's manual source of truth — the
# ContactResults buttons write to it. If it's set to one of the terminal
# manual values we honor it BEFORE re-deriving from signal flags, otherwise
# the read path would silently override what the write path just stored.
# "Sent" / "No response" intentionally do NOT auto-advance the pipeline stage.
# Won / Lost flags still win over outreach (a closed deal is closed).
def _derive_status(opp: Dict[str, Any]) -> str:
    if opp.get("flag_won"):
        return "Won"
    if opp.get("outcome"):
        return "Lost"

    outreach = opp.get("outreach_status")
    if isinstance(outreach, str) and outreach.strip():
        ol = outreach.lower().strip()
        if "not interested" in ol or "do not contact" in ol:
            return "Disqualified"
        if "estimate requested" in ol:
            return "Estimate requested"
        if ol in ("replied", "reply received") or "reply received" in ol:
            return "Conversation started"
        # "sent", "no response", "not sent", "sms draft" — fall through

    reply = opp.get("reply_classification")
    if isinstance(reply, str) and reply.strip():
        rl = reply.lower().strip()
        if "not interested" in rl:
            return "Disqualified"

    if opp.get("flag_estimate"):
        return "Estimate sent"
    if opp.get("flag_reply_received") or opp.get("flag_positive_conversation"):
        return "Conversation started"
    if opp.get("flag_outreach_sent"):
        return "Estimate requested"
    appr = (opp.get("approval_status") or "").lower() if isinstance(opp.get("approval_status"), str) else ""
    if "approved" in appr:
        return "Ready"
    enrich = (opp.get("enrichment_status") or "").lower() if isinstance(opp.get("enrichment_status"), str) else ""
    if "needs research" in enrich or "research" in enrich:
        return "Needs research"
    raw = (opp.get("status_raw") or "") if isinstance(opp.get("status_raw"), str) else ""
    if raw:
        return raw
    return "New"


# Priority score is the canonical Airtable `Lead score`. Do NOT synthesise —
# a missing value means "needs scoring", never zero, never a fake value.
def _derive_priority_score(opp: Dict[str, Any]) -> Optional[float]:
    raw = opp.get("lead_score")
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Lane classification — three parallel funnels the dashboard ranks across.
#   market_capture   — permit-driven qualified project leads (the default)
#   partner          — contractors/designers/architects/suppliers/referrers
#   non_permit       — public non-permit signals (website, social, referral…)
# ---------------------------------------------------------------------------
LANES = ("market_capture", "partner", "non_permit")

LANE_LABELS = {
    "market_capture": "Market Capture",
    "partner": "Partner Pipeline",
    "non_permit": "Non-Permit Signals",
}

_PARTNER_TYPE_TOKENS = (
    "contractor", "remodel", "designer", "architect",
    "supplier", "vendor", "referral", "partner",
)
_PARTNER_SOURCE_TOKENS = ("partner", "referral", "network", "trade")


def _derive_lane(opp: Dict[str, Any]) -> str:
    if opp.get("flag_partnership") is True:
        return "partner"
    otype = (opp.get("project_type") or "")
    otype_l = otype.lower() if isinstance(otype, str) else ""
    if any(tok in otype_l for tok in _PARTNER_TYPE_TOKENS):
        return "partner"
    src_cat = (opp.get("source_category") or "")
    src_cat_l = src_cat.lower() if isinstance(src_cat, str) else ""
    if any(tok in src_cat_l for tok in _PARTNER_SOURCE_TOKENS):
        return "partner"
    src = (opp.get("source") or "")
    src_l = src.lower() if isinstance(src, str) else ""
    if any(tok in src_l for tok in _PARTNER_SOURCE_TOKENS):
        return "partner"
    if src_l and "permit" not in src_l and "permit" not in src_cat_l:
        return "non_permit"
    return "market_capture"


def _derive_priority_band(opp: Dict[str, Any]) -> Optional[str]:
    # Honour explicit Airtable Priority if set.
    b = _normalize_priority_band(opp.get("priority_raw"))
    if b:
        return b
    s = opp.get("priority_score")
    if s is None:
        return None
    try:
        s = float(s)
    except (TypeError, ValueError):
        return None
    if s >= 70:
        return "A"
    if s >= 50:
        return "B"
    if s >= 30:
        return "C"
    return "D"


def _derive_daily_mission(opp: Dict[str, Any]) -> str:
    # Prefer the recommended action / next best action free text.
    for source in ("next_best_action", "recommended_action", "recommended_offer",
                   "outreach_angle"):
        v = opp.get(source)
        if v:
            m = _normalize_daily_mission(v)
            if m != "Wait":
                return m
    # Fall back to channel hints.
    for src in ("best_contact_method", "outreach_channel", "preferred_contact_method"):
        v = opp.get(src)
        if v:
            m = _normalize_daily_mission(v)
            if m != "Wait":
                return m
    # Enrichment-heavy leads without a message yet -> Research First.
    enrich = (opp.get("enrichment_status") or "").lower() if isinstance(opp.get("enrichment_status"), str) else ""
    if "needs research" in enrich or "research" in enrich:
        return "Research First"
    return "Wait"


# Contact confidence — pyairtable can return string or number for this select.
def _normalize_contact_confidence(v: Any) -> Optional[str]:
    if v is None or v == "":
        return None
    return str(v)

ACTIONABLE_MISSIONS = [
    "Call Today",
    "Send Text",
    "Send Email",
    "Research First",
    "Visit Property",
    "Prepare Estimate",
    "Ask for Referral",
    "Follow Up",
    "Wait",
]


def _to_list(value: Any) -> List[Any]:
    """Coerce Airtable multi-select / string values to a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        # comma-separated fallback
        parts = [p.strip() for p in value.split(",") if p.strip()]
        return parts
    return [value]


def _first(value: Any) -> Optional[Any]:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _normalize_priority_band(v: Any) -> Optional[str]:
    """Map any Airtable formula output to A/B/C/D bands for UI coloring.
    Aligned to the Bloodhound base band vocabulary:
      🟢 High Priority     -> A
      🟡 Good Opportunity  -> B
      🟠 Research First    -> C
      🔴 Low Priority      -> D
      ⚪ Not Scored Yet    -> None (no band)
    """
    if v is None or v == "":
        return None
    s = str(v).lower()
    if "not scored" in s or "unscored" in s:
        return None
    # Order matters: check specific first.
    if "medium-high" in s or "medium high" in s:
        return "B"
    if "high" in s:
        return "A"
    if "good" in s:
        return "B"
    if "medium" in s:
        return "C"
    if "research" in s:
        return "C"
    if "low" in s:
        return "D"
    if s.strip() in {"a", "b", "c", "d"}:
        return s.strip().upper()
    return None


_MISSION_KEYWORDS = [
    ("Call Today", ("call today", "call now", "call the")),
    ("Send Text", ("text", "sms")),
    ("Send Email", ("email",)),
    ("Research First", ("research",)),
    ("Visit Property", ("visit", "site visit", "walk")),
    ("Prepare Estimate", ("estimate", "quote", "bid")),
    ("Ask for Referral", ("referral", "intro", "introduction")),
    ("Follow Up", ("follow up", "follow-up", "check in", "check-in")),
    ("Wait", ("wait", "not assigned", "unassigned", "hold", "monitor")),
]


def _normalize_daily_mission(v: Any) -> str:
    """Map any Airtable formula output to one of the 9 mission buckets."""
    if v is None or v == "":
        return "Wait"
    s = str(v).lower()
    for bucket, keywords in _MISSION_KEYWORDS:
        if any(k in s for k in keywords):
            return bucket
    return "Wait"


def _strip_emoji_prefix(v: Any) -> Any:
    """For display, strip a leading emoji+space if present."""
    if not isinstance(v, str):
        return v
    parts = v.split(" ", 1)
    if len(parts) == 2 and not parts[0].isascii():
        return parts[1].strip()
    return v


class AirtableOpportunityService:
    backend_name = "airtable"

    def __init__(self, api_key: str, base_id: str, table_name: str, cache_ttl: float = 45.0):
        self._api = Api(api_key)
        self._base_id = base_id
        self._table_name = table_name
        self._table = self._api.table(base_id, table_name)
        self._cache_ttl = cache_ttl
        self._lock = threading.Lock()
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._last_refresh: float = 0.0
        self._refresh_started: float = 0.0
        self._refreshing: bool = False
        self._last_error: Optional[str] = None
        self._last_error_ts: float = 0.0
        self._consecutive_failures: int = 0
        self._readonly_field_names: set = set()
        self._field_map: Dict[str, str] = {}
        self._reverse_map: Dict[str, str] = {}
        self._load_schema()

    # ---------- schema ----------
    def _load_schema(self) -> None:
        """Fetch base schema and build a mapping restricted to real fields."""
        try:
            base = self._api.base(self._base_id)
            schema = base.schema()
            table = next(
                (t for t in schema.tables if t.name == self._table_name or t.id == self._table_name),
                None,
            )
            if table is None:
                raise RuntimeError(
                    f"Airtable table '{self._table_name}' not found in base '{self._base_id}'"
                )

            available = {}
            for f in table.fields:
                available[f.name] = f
                if getattr(f, "type", None) in READONLY_FIELD_TYPES:
                    self._readonly_field_names.add(f.name)

            # The user has explicitly requested certain formula/system fields
            # be treated as read-only even if the schema type didn't flag them.
            for name in EXPLICIT_READONLY:
                if name in available:
                    self._readonly_field_names.add(name)

            self._field_map = {
                airtable_name: snake
                for airtable_name, snake in KNOWN_FIELD_MAP.items()
                if airtable_name in available
            }
            self._reverse_map = {v: k for k, v in self._field_map.items()}

            missing = sorted(set(KNOWN_FIELD_MAP) - set(self._field_map))
            if missing:
                log.info("Airtable: %d expected fields not present in schema (will render as 'Not available yet'): %s",
                         len(missing), ", ".join(missing))
            log.info("Airtable: schema loaded — %d fields mapped, %d read-only",
                     len(self._field_map), len(self._readonly_field_names))
        except Exception as e:
            log.exception("Airtable: failed to load schema")
            raise

    def schema_report(self) -> Dict[str, Any]:
        return {
            "base_id": self._base_id,
            "table_name": self._table_name,
            "mapped_fields": [
                {"airtable": at, "internal": sn, "readonly": at in self._readonly_field_names}
                for at, sn in sorted(self._field_map.items())
            ],
            "unmapped_expected": sorted(
                set(KNOWN_FIELD_MAP) - set(self._field_map)
            ),
            "editable_allowlist": sorted(
                f for f in EDITABLE_FIELDS
                if f in self._field_map and f not in self._readonly_field_names
            ),
        }

    # ---------- record transform ----------
    def _record_to_opportunity(self, record: Dict[str, Any]) -> Dict[str, Any]:
        fields = record.get("fields", {}) or {}
        opp: Dict[str, Any] = {"id": record.get("id")}
        for at_name, snake in self._field_map.items():
            opp[snake] = fields.get(at_name)

        # created_time: prefer Airtable metadata (guaranteed present) over the
        # user-visible "Created time" field which may be re-typed.
        opp["created_time"] = opp.get("created_time") or record.get("createdTime")

        # opportunity_id fallback: Airtable record id.
        opp["opportunity_id"] = opp.get("opportunity_id") or opp["id"]

        # Coerce list-typed fields
        opp["missing_information"] = _to_list(opp.get("missing_information"))
        opp["risk_flags"] = _to_list(opp.get("risk_flags"))

        # Some fields may come back as arrays from linked-record / rollup formulas
        for k in ("source", "signal_type", "project_type", "status_raw",
                  "priority_raw", "revenue_potential", "outcome",
                  "approval_status", "outreach_status", "hunt_status",
                  "enrichment_status", "reply_classification",
                  "best_contact_method", "preferred_contact_method",
                  "outreach_channel", "source_category",
                  "contact_confidence_raw"):
            if isinstance(opp.get(k), list):
                opp[k] = _first(opp[k])

        # Ensure numeric types where sensible
        for k in ("lead_score", "confidence_score", "estimated_value",
                  "closed_revenue", "estimated_gross_profit"):
            v = opp.get(k)
            if isinstance(v, list):
                v = _first(v)
            try:
                opp[k] = float(v) if v not in (None, "", []) else None
                if opp[k] is not None and opp[k].is_integer():
                    opp[k] = int(opp[k])
            except (TypeError, ValueError):
                opp[k] = None

        # ---- derived fields the dashboard consumes ----
        # Contact confidence rendered as a string label the UI already handles.
        opp["contact_confidence"] = _normalize_contact_confidence(opp.get("contact_confidence_raw"))
        # Evidence confidence — reuse Confidence score when present, else lead score.
        opp["evidence_confidence"] = opp.get("confidence_score") or opp.get("lead_score")

        # Priority — synthesise until Airtable starts scoring.
        opp["priority_score"] = _derive_priority_score(opp)
        opp["priority_band_raw"] = opp.get("priority_raw")
        opp["priority_band"] = _derive_priority_band(opp)

        # Daily mission — synthesise from Next action + channel hints.
        opp["daily_mission_raw"] = opp.get("next_best_action")
        opp["daily_mission"] = _derive_daily_mission(opp)
        opp["daily_mission_code"] = None

        # Recommended action fallback — prefer AI's "recommended action" over
        # the shorter "Next action", but expose both.
        if not opp.get("recommended_action"):
            opp["recommended_action"] = opp.get("next_best_action")
        opp["recommended_action_code"] = None

        # Dashboard pipeline status — collapse Leads workflow onto the 9 stages.
        opp["status"] = _derive_status(opp)
        if isinstance(opp["status"], str):
            opp["status_raw_display"] = _strip_emoji_prefix(opp["status"])
            opp["status"] = _strip_emoji_prefix(opp["status"])

        # Legacy "Ryans decision" field maps to Hunt status.
        opp["ryans_decision"] = opp.get("hunt_status")

        # Fit / momentum / reachability — derived qualitative labels the UI shows.
        rev = (opp.get("revenue_potential") or "").lower() if isinstance(opp.get("revenue_potential"), str) else ""
        if "high" in rev:
            opp["opportunity_fit"] = "Strong"
        elif "medium" in rev or "med" in rev:
            opp["opportunity_fit"] = "Moderate"
        elif "low" in rev:
            opp["opportunity_fit"] = "Weak"
        else:
            opp["opportunity_fit"] = None

        opp["momentum"] = "High" if opp.get("flag_recent_activity") else (
            "Stalled" if opp.get("flag_won") or opp.get("outcome") else "Normal"
        )

        # Lane classification (market_capture / partner / non_permit)
        opp["lane"] = _derive_lane(opp)
        opp["lane_label"] = LANE_LABELS.get(opp["lane"], opp["lane"])

        if opp.get("phone") or opp.get("email") or opp.get("phone_alt") or opp.get("email_alt"):
            opp["reachability"] = "Direct"
        elif opp.get("company") or opp.get("website"):
            opp["reachability"] = "Indirect"
        else:
            opp["reachability"] = "Unknown"

        # Ensure every downstream key exists so the frontend never crashes on
        # missing schema fields.
        for snake in set(KNOWN_FIELD_MAP.values()):
            opp.setdefault(snake, None)
        for extra in ("priority_score", "priority_band", "daily_mission",
                      "status", "ryans_decision", "opportunity_fit",
                      "momentum", "reachability", "contact_confidence",
                      "evidence_confidence", "recommended_action_code",
                      "daily_mission_code"):
            opp.setdefault(extra, None)

        # Synthetic activity timeline (real timestamps only, no invented events)
        opp["activity_timeline"] = self._synthesize_activity(opp)
        return opp

    def _synthesize_activity(self, opp: Dict[str, Any]) -> List[Dict[str, Any]]:
        timeline: List[Dict[str, Any]] = []
        if opp.get("created_time"):
            src = opp.get("source") or "signal"
            timeline.append({
                "type": "discovered",
                "note": f"Discovered via {src}",
                "timestamp": opp["created_time"],
            })
        if opp.get("validated_at"):
            timeline.append({
                "type": "analysis",
                "note": "Lead validated",
                "timestamp": opp["validated_at"],
            })
        if opp.get("message_generated_at"):
            timeline.append({
                "type": "message",
                "note": "AI drafted outbound message",
                "timestamp": opp["message_generated_at"],
            })
        if opp.get("message_sent_date"):
            timeline.append({
                "type": "outreach",
                "note": "Outreach sent",
                "timestamp": opp["message_sent_date"],
            })
        if opp.get("date_replied"):
            timeline.append({
                "type": "reply",
                "note": opp.get("reply_summary") or "Reply received",
                "timestamp": opp["date_replied"],
            })
        if opp.get("last_reviewed") and opp.get("status") and opp["status"] != "New":
            timeline.append({
                "type": "status_change",
                "note": f"Current status: {opp['status']}",
                "timestamp": opp["last_reviewed"],
            })
        # newest first
        timeline.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
        return timeline

    # ---------- cache ----------
    RETRY_DELAYS = [0.0, 1.0, 2.5]  # up to 3 attempts, ~3.5s worst case

    def _refresh_cache(self, force: bool = False) -> None:
        now = time.time()
        if not force and (now - self._last_refresh) < self._cache_ttl and self._cache:
            return
        with self._lock:
            self._refreshing = True
            self._refresh_started = now

        last_exc: Optional[BaseException] = None
        for attempt, delay in enumerate(self.RETRY_DELAYS, start=1):
            if delay:
                time.sleep(delay)
            try:
                records = self._table.all()
                new_cache: Dict[str, Dict[str, Any]] = {}
                for r in records:
                    dto = self._record_to_opportunity(r)
                    rid = dto.get("id")
                    if rid:
                        new_cache[rid] = dto
                with self._lock:
                    self._cache = new_cache
                    self._last_refresh = time.time()
                    self._refreshing = False
                    self._last_error = None
                    self._last_error_ts = 0.0
                    self._consecutive_failures = 0
                if attempt > 1:
                    log.info("Airtable: refresh recovered on attempt %d", attempt)
                return
            except Exception as e:  # noqa: BLE001
                last_exc = e
                log.warning("Airtable: refresh attempt %d/%d failed: %s",
                            attempt, len(self.RETRY_DELAYS), e)

        # All attempts failed — mark state and either serve stale or raise.
        with self._lock:
            self._refreshing = False
            self._consecutive_failures += 1
            self._last_error = (str(last_exc) or last_exc.__class__.__name__)[:240]
            self._last_error_ts = time.time()
            have_cache = bool(self._cache)
        log.error("Airtable: refresh failed after %d attempts (%d consecutive): %s",
                  len(self.RETRY_DELAYS), self._consecutive_failures, last_exc)
        if have_cache:
            # Serve stale data rather than break the UI.
            return
        if last_exc is not None:
            raise last_exc

    def cache_status(self) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            last = self._last_refresh
            refreshing = self._refreshing
            count = len(self._cache)
            last_error = self._last_error
            last_error_ts = self._last_error_ts
            failures = self._consecutive_failures
        age = (now - last) if last else None
        stale = age is None or age > self._cache_ttl
        return {
            "backend": self.backend_name,
            "count": count,
            "last_refresh": datetime.fromtimestamp(last, tz=timezone.utc).isoformat() if last else None,
            "age_seconds": age,
            "ttl_seconds": self._cache_ttl,
            "next_refresh_in": max(0.0, self._cache_ttl - age) if age is not None else 0.0,
            "is_stale": stale,
            "is_refreshing": refreshing,
            "last_error": last_error,
            "last_error_at": datetime.fromtimestamp(last_error_ts, tz=timezone.utc).isoformat() if last_error_ts else None,
            "consecutive_failures": failures,
        }

    def force_refresh(self) -> Dict[str, Any]:
        try:
            self._refresh_cache(force=True)
        except Exception:
            # cache_status() will already reflect the error state.
            pass
        return self.cache_status()

    def _all_cached(self) -> List[Dict[str, Any]]:
        self._refresh_cache()
        with self._lock:
            return [deepcopy(v) for v in self._cache.values()]

    # ---------- reads ----------
    def count(self) -> int:
        return len(self._all_cached())

    def all(self) -> List[Dict[str, Any]]:
        return self._all_cached()

    def get(self, opp_id: str) -> Optional[Dict[str, Any]]:
        self._refresh_cache()
        with self._lock:
            cached = self._cache.get(opp_id)
            if cached:
                return deepcopy(cached)
        # not in cache, try single-record fetch
        try:
            rec = self._table.get(opp_id)
        except Exception:
            return None
        if not rec:
            return None
        dto = self._record_to_opportunity(rec)
        with self._lock:
            self._cache[dto["id"]] = dto
        return deepcopy(dto)

    def list(self, source=None, status=None, priority_band=None,
             daily_mission=None, project_type=None, min_score=None,
             q=None, lane=None, sort=None) -> List[Dict[str, Any]]:
        results = self._all_cached()
        if source:
            results = [o for o in results if o.get("source") == source]
        if status:
            results = [o for o in results if o.get("status") == status]
        if priority_band:
            results = [o for o in results if o.get("priority_band") == priority_band]
        if daily_mission:
            results = [o for o in results if o.get("daily_mission") == daily_mission]
        if project_type:
            results = [o for o in results if o.get("project_type") == project_type]
        if lane:
            results = [o for o in results if o.get("lane") == lane]
        if min_score is not None:
            # Only filter records that HAVE a score; unscored are dropped when
            # a min-score threshold is set (we can't compare "Needs scoring").
            results = [o for o in results
                       if isinstance(o.get("priority_score"), (int, float))
                       and o["priority_score"] >= float(min_score)]
        if q:
            ql = q.lower()
            def match(o):
                blob = " ".join([
                    str(o.get("name", "")),
                    str(o.get("opportunity_id", "")),
                    str(o.get("project_address", "")),
                    str(o.get("decision_maker", "")),
                    str(o.get("permit_number", "")),
                    str(o.get("project_type", "")),
                ]).lower()
                return ql in blob
            results = [o for o in results if match(o)]
        return sort_opportunities(results, mode=sort or "lead_score")

    def top(self, limit: int = 10) -> List[Dict[str, Any]]:
        active = [o for o in self._all_cached() if o.get("status") not in CLOSED_STATUSES]
        return sort_opportunities(active, mode="lead_score")[:limit]

    def recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        items = self._all_cached()
        items.sort(key=lambda o: o.get("created_time") or "", reverse=True)
        return items[:limit]

    def summary(self) -> Dict[str, Any]:
        all_ops = self._all_cached()
        active = [o for o in all_ops if o.get("status") not in CLOSED_STATUSES]
        immediate = [o for o in active if o.get("daily_mission") in
                     ("Call Today", "Send Text", "Visit Property")]
        ready = [o for o in active if o.get("status") == "Ready"]
        needs_research = [o for o in active
                          if o.get("status") == "Needs research"
                          or o.get("daily_mission") == "Research First"]
        new_ops = [o for o in all_ops if o.get("status") == "New"]
        pipeline_value = sum([(o.get("estimated_value") or 0) for o in active])
        return {
            "new_opportunities": len(new_ops),
            "immediate_action": len(immediate),
            "ready_to_contact": len(ready),
            "needs_research": len(needs_research),
            "total_pipeline_value": pipeline_value,
            "active_count": len(active),
            "total_count": len(all_ops),
        }

    def group_by_mission(self) -> Dict[str, List[Dict[str, Any]]]:
        groups: Dict[str, List[Dict[str, Any]]] = {m: [] for m in ACTIONABLE_MISSIONS}
        for o in self._all_cached():
            if o.get("status") in CLOSED_STATUSES:
                continue
            mission = o.get("daily_mission")
            if mission in groups:
                groups[mission].append(o)
        for m in groups:
            groups[m] = sort_opportunities(groups[m], mode="lead_score")
        return groups

    def pipeline_counts(self) -> List[Dict[str, Any]]:
        counts = {s: 0 for s in PIPELINE_STATUSES}
        values = {s: 0.0 for s in PIPELINE_STATUSES}
        for o in self._all_cached():
            s = o.get("status")
            if s in counts:
                counts[s] += 1
                values[s] += (o.get("estimated_value") or 0)
        return [
            {"status": s, "count": counts[s], "value": values[s]}
            for s in PIPELINE_STATUSES
        ]

    # ---------- writes (whitelist) ----------
    def _writable_airtable_fields(self, updates_by_snake: Dict[str, Any]) -> Dict[str, Any]:
        """Filter snake_case updates down to Airtable fields we're allowed to write."""
        allowed: Dict[str, Any] = {}
        rejected: List[str] = []
        for snake, val in updates_by_snake.items():
            at_name = WRITE_ALIAS.get(snake) or self._reverse_map.get(snake)
            if not at_name:
                rejected.append(snake)
                continue
            if at_name not in EDITABLE_FIELDS:
                rejected.append(snake)
                continue
            if at_name in self._readonly_field_names:
                rejected.append(snake)
                continue
            allowed[at_name] = val
        if rejected:
            log.info("Airtable: ignoring non-editable fields: %s", rejected)
        return allowed

    def update_fields(self, opp_id: str, updates_by_snake: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = self._writable_airtable_fields(updates_by_snake)
        if not allowed:
            return self.get(opp_id)
        # Coerce empty strings to None so the caller can CLEAR a date / select
        # field instead of Airtable rejecting the empty value.
        allowed = {k: (None if v == "" else v) for k, v in allowed.items()}
        try:
            # typecast=True lets Airtable auto-add new single-select options when
            # the PAT is base-editor. Falls back to normal 422 otherwise.
            self._table.update(opp_id, allowed, typecast=True)
        except Exception as e:
            log.exception("Airtable: update failed for %s", opp_id)
            status = 422
            detail = str(e)
            resp = getattr(e, "response", None)
            if resp is not None:
                status = getattr(resp, "status_code", status) or status
                try:
                    body = resp.json()
                    if isinstance(body, dict) and "error" in body:
                        err = body["error"]
                        if isinstance(err, dict):
                            detail = err.get("message") or err.get("type") or detail
                        else:
                            detail = str(err)
                except Exception:
                    pass
            raise AirtableWriteError(detail, status_code=status) from e
        # Force cache refresh so subsequent reads pick up formula recomputation.
        self._refresh_cache(force=True)
        return self.get(opp_id)

    def update_status(self, opp_id: str, status: str) -> Optional[Dict[str, Any]]:
        return self.update_fields(opp_id, {"status": status})

    def update_mission(self, opp_id: str, mission: str) -> Optional[Dict[str, Any]]:
        # Daily Mission is a formula field in the base — writes are rejected.
        # Kept for API compatibility; the value is stored as a request-time
        # override on the cached record only, never persisted.
        with self._lock:
            cached = self._cache.get(opp_id)
            if cached:
                cached["daily_mission"] = mission
                return deepcopy(cached)
        return self.get(opp_id)

    def add_activity(self, opp_id: str, type_: str, note: Optional[str]) -> Optional[Dict[str, Any]]:
        # No Interactions table yet — record in-memory only so the UI stays live.
        with self._lock:
            cached = self._cache.get(opp_id)
            if not cached:
                return None
            timeline = cached.setdefault("activity_timeline", [])
            timeline.insert(0, {
                "type": type_,
                "note": note or "",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return deepcopy(cached)


_last_build_error: Optional[str] = None


def get_last_build_error() -> Optional[str]:
    """Return the last Airtable-init exception message so /api/config can
    surface it (e.g. '401 Unauthorized', 'table not found'). None until an
    init has been attempted or if the last init succeeded."""
    return _last_build_error


def build_airtable_service_from_env() -> Optional[AirtableOpportunityService]:
    global _last_build_error
    api_key = os.environ.get("AIRTABLE_API_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    table = os.environ.get("AIRTABLE_OPPORTUNITIES_TABLE")
    enabled = os.environ.get("AIRTABLE_ENABLED", "").lower() == "true"
    if not (enabled and api_key and base_id and table):
        _last_build_error = None
        return None
    try:
        svc = AirtableOpportunityService(api_key, base_id, table)
        _last_build_error = None
        return svc
    except Exception as e:  # noqa: BLE001
        log.exception("Airtable: initialization failed — falling back to sample data")
        msg = str(e)
        # Trim to the useful signal without leaking the PAT.
        if "401" in msg or "Unauthorized" in msg:
            _last_build_error = (
                "401 Unauthorized — Airtable PAT is invalid or revoked. "
                "Rotate the token in Airtable → Developer Hub → Personal "
                "access tokens, then update AIRTABLE_API_KEY."
            )
        elif "403" in msg:
            _last_build_error = (
                "403 Forbidden — PAT lacks required scopes. Needs "
                "data.records:read, data.records:write, schema.bases:read "
                "and access to the Bloodhound base."
            )
        elif "404" in msg or "NOT_FOUND" in msg:
            _last_build_error = (
                "404 Not Found — AIRTABLE_BASE_ID or AIRTABLE_OPPORTUNITIES_TABLE "
                "does not match a base/table this PAT can see."
            )
        else:
            _last_build_error = f"{type(e).__name__}: {msg[:220]}"
        return None
