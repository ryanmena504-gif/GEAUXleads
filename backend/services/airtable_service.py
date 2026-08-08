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

from services import aggregations, dedupe, ingestion_diagnostics

log = logging.getLogger("bloodhound.airtable")


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
    # Keep the two money concepts separate. A permit amount is the published
    # total project value, while the AI estimate is only the possible portion
    # of that project that could become Shirtless Handyman work.
    "Permit project value": "construction_value",
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
    "First message": "first_message",
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
    "Reply summary",
    "Reply classification",
    "Verified opportunity",
    "Qualified opportunity",
    "Outreach sent",
    "Reply received",
    "Positive conversation",
    "Estimate opportunity",
    "Job won",
    "Closed revenue",
    "Estimated gross profit",
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

# Statuses / stages / missions live in services.aggregations so both backends
# agree on what a count means. Re-exported here for existing importers.
CLOSED_STATUSES = set(aggregations.CLOSED_STATUSES)
PIPELINE_STATUSES = aggregations.PIPELINE_STATUSES


# Derive a dashboard-pipeline stage from the Leads workflow state.
def _derive_status(opp: Dict[str, Any]) -> str:
    if opp.get("flag_won"):
        return "Won"
    if opp.get("outcome"):
        return "Lost"
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


# Derive a 0-100 priority score from what the Leads table actually populates.
# Real Lead score / Confidence score are almost always 0 in this base, so we
# synthesise from richness signals until the automation starts scoring.
def _derive_priority_score(opp: Dict[str, Any]) -> Optional[float]:
    raw = opp.get("lead_score")
    try:
        if raw is not None and float(raw) > 0:
            return float(raw)
    except (TypeError, ValueError):
        pass
    score = 0
    if (opp.get("ai_status") or "").lower() == "complete":
        score += 35
    if opp.get("evidence_summary"):
        score += 10
    if opp.get("recommendation_reason"):
        score += 5
    if opp.get("phone") or opp.get("email") or opp.get("phone_alt") or opp.get("email_alt"):
        score += 15
    if opp.get("decision_maker") or opp.get("company"):
        score += 10
    if opp.get("permit_number"):
        score += 10
    if opp.get("project_address"):
        score += 5
    if opp.get("estimated_value"):
        score += 5
    if opp.get("flag_verified"):
        score += 5
    if opp.get("flag_qualified"):
        score += 5
    if opp.get("flag_premium"):
        score += 3
    if opp.get("flag_partnership"):
        score += 2
    return score if score > 0 else None


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

ACTIONABLE_MISSIONS = aggregations.ACTIONABLE_MISSIONS


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
        self._schema_field_names: List[str] = []
        self._duplicate_index: Dict[str, Any] = {"by_record": {}, "groups": {}}
        self._ingestion = ingestion_diagnostics.IngestionRecorder()
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
            self._schema_field_names = sorted(available)

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
        for k in ("lead_score", "confidence_score", "construction_value",
                  "estimated_value", "closed_revenue", "estimated_gross_profit"):
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
                self._ingestion.start()
                for r in records:
                    self._ingestion.record_seen()
                    # One malformed record must not take the whole refresh down,
                    # but the loss has to be visible — see /api/diagnostics/ingestion.
                    try:
                        dto = self._record_to_opportunity(r)
                    except Exception as exc:  # noqa: BLE001
                        self._ingestion.record_failure(r.get("id"), exc)
                        continue
                    rid = dto.get("id")
                    if rid:
                        new_cache[rid] = dto
                        self._ingestion.record_projected()
                self._ingestion.finish()
                index = dedupe.annotate(list(new_cache.values()))
                with self._lock:
                    self._cache = new_cache
                    self._duplicate_index = index
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
             q=None, include_duplicates: bool = False) -> List[Dict[str, Any]]:
        return aggregations.filter_records(
            self._all_cached(), source=source, status=status,
            priority_band=priority_band, daily_mission=daily_mission,
            project_type=project_type, min_score=min_score, q=q,
            include_duplicates=include_duplicates,
        )

    def top(self, limit: int = 10) -> List[Dict[str, Any]]:
        return aggregations.top(self._all_cached(), limit=limit)

    def recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        return aggregations.recent(self._all_cached(), limit=limit)

    def summary(self) -> Dict[str, Any]:
        return aggregations.summary(self._all_cached())

    def group_by_mission(self) -> Dict[str, List[Dict[str, Any]]]:
        return aggregations.group_by_mission(self._all_cached())

    def pipeline_counts(self) -> List[Dict[str, Any]]:
        return aggregations.pipeline_counts(self._all_cached())

    # ---------- duplicates & diagnostics ----------
    def duplicates_report(self) -> Dict[str, Any]:
        self._refresh_cache()
        with self._lock:
            index = deepcopy(self._duplicate_index)
        return dedupe.duplicate_report(index)

    def ingestion_report(self) -> Dict[str, Any]:
        records = self._all_cached()
        with self._lock:
            index = deepcopy(self._duplicate_index)
        return ingestion_diagnostics.build_report(
            records=records,
            field_map=self._field_map,
            known_field_map=KNOWN_FIELD_MAP,
            schema_field_names=self._schema_field_names,
            pipeline_report=self._ingestion.report(),
            duplicates=dedupe.duplicate_report(index),
        )

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
        try:
            self._table.update(opp_id, allowed)
        except Exception:
            log.exception("Airtable: update failed for %s", opp_id)
            raise
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


def build_airtable_service_from_env() -> Optional[AirtableOpportunityService]:
    api_key = os.environ.get("AIRTABLE_API_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    table = os.environ.get("AIRTABLE_OPPORTUNITIES_TABLE")
    enabled = os.environ.get("AIRTABLE_ENABLED", "").lower() == "true"
    if not (enabled and api_key and base_id and table):
        return None
    try:
        return AirtableOpportunityService(api_key, base_id, table)
    except Exception:
        log.exception("Airtable: initialization failed — falling back to sample data")
        return None
