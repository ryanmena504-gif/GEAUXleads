"""
Raw Signals your AI already approved, waiting to reach your list.

The Make scenario "qualified signals to dashboard leads" is supposed to move
AI-approved permits (AI Decision = ready_for_campaign_review /
ready_for_outreach) into Leads every morning. Since late August it has run
daily and promoted nothing, so approved jobs sat in Raw Signals unseen.

This service lets Ryan do that step himself, one record at a time:
  • promote — creates the Lead with the SAME field mapping the Make scenario
    uses (blueprint of scenario 5831989), links it back to the signal, and
    marks the signal "Promoted to Leads" so Make never duplicates it.
  • pass    — marks the signal "Passed by Ryan: <reason>" so it leaves the
    queue and the learning loop sees why.

Nothing is sent to anyone. Field IDs are used because several Leads field
names carry trailing spaces.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from services.airtable_client import make_api
from services.rejection_service import reason_for

log = logging.getLogger("bloodhound.promotion")

RAW_SIGNALS_TABLE = "Raw Signals"

# Raw Signals field IDs
R = {
    "signal_id": "fldmG6goF98m3NjCB",
    "source_record_id": "fldJ059Shizlisfjs",
    "jurisdiction": "fldBchYZbrfDbttZ4",
    "status_raw": "fldLZjFP9G2Iw0hms",
    "work_class": "fldbBT36xDdBfAQoQ",
    "description": "flduyAE404knvmNL5",
    "address": "fldo7CvuCgQP6DBQy",
    "parcel_id": "fldwFmEalqGn1hImU",
    "contractor": "fldavTX2A6Vrp6d5u",
    "estimated_value": "fldYjUdnF404GYxAV",
    "event_date": "fldTRV3UMlfoXgpYn",
    "source_url": "fld2H0RgTJTfkScka",
    "promotion_status": "fldRT46IGzF230SzE",
    "score": "fldKCcDiPdnlHno1r",
    "tier": "fldRBaSd3RViLWqVJ",
    "ai_confidence": "fld8WPkGoekCZoeR6",
    "ai_value": "fldSdhvXs8XZ8y6q4",
    "ai_reasons": "fld80Q3ZYEYTOCibC",
    "ai_decision": "fldqwmMObFaUe5avE",
    "ai_project_type": "fldaYfFIwrE4m7cn5",
    "ai_next_action": "fldXA95HyQ18S9FI8",
    "ai_service_fit": "fldSg51YCSzDKNUyc",
}

# Leads field IDs (from the Make scenario's create-record mapping)
L = {
    "name": "fld7qBIbdbxakOJ4L",            # Leads Name
    "address": "fld6flPEL5A4yTd9H",         # Address
    "city": "fld5UpspaR6sNbkf2",            # City
    "confidence": "fld2H2E7WeeBTaoWm",      # Confidence score
    "evidence": "fld2OmMSHHkJ8MaFE",        # Evidence summary
    "risk_flags": "fld7TAIyY2204PgBU",      # Risk flags
    "opportunity_type": "fld8XeP3Wrg4HXvsb",
    "estimated_job_value": "fldAHk6I3yfiJ6WCB",
    "ai_summary": "fldAVQlqxBakvH7ie",
    "permit_value": "fldB1wORNDOxu8t6t",
    "permit_status": "fldFTF3g8O4GP7iV8",
    "source_url": "fldK77qr5LqnAKj8I",
    "source_category": "fldN0xA1z58TNG4ps",
    "hunt_status": "fldOCAeOdXfdQbk2i",
    "external_id": "fldQTuXJPp2VO5KYP",     # ID
    "recent_activity": "fldR9ZIZ8xKewRCtw",
    "contact_company": "fldSLAN9DJAHIWJjV",
    "enrichment_status": "fldSVi0MjchZ3A4gF",
    "why_matters": "fldUooAWcaIyf91Mc",
    "permit_event_date": "fldXpPKOy6CLvDtnQ",
    "priority": "fldbEIuUbulfICSxJ",
    "lead_score": "fldftXGI9rJ9iMaav",
    "qualified": "fldhTrE46bJ3FxiDa",
    "permit_description": "fldifB9dCaPdJ7O9l",
    "permit_number": "fldlV4cXCx1OEtxuY",
    "parcel_id": "fldoTDieRiqfnzKJ5",
    "local_service_area": "fldtjWTycKM3ux1bm",
    "status": "flduCCK1WKS7Zo94D",
    "signal_found": "fldvxGAguk2m1V39N",
    "source": "fldwcu8FwzT0oVjKW",
    "next_action": "fldyLz6quR9U0trYn",
    "raw_signals": "fldw04qtvDxb37cph",     # link back to the signal
    "needs_classification": "fldiPaH928NreBHHJ",
}

RISK_FLAGS = (
    "Public permit evidence is project intelligence only. Any business or homeowner "
    "email must have a retained public/permitted source, retrieval date, and "
    "project-fit rationale. A permit alone never authorizes contact; outbound email "
    "requires an approved campaign."
)

# Approved by the AI, not yet promoted, not disqualified, not passed.
WAITING_FORMULA = (
    "AND("
    "OR({AI Decision}='ready_for_campaign_review',{AI Decision}='ready_for_outreach'),"
    "OR({Promotion Status}='AI Decided',{Promotion Status}='Raw',{Promotion Status}='')"
    ")"
)

PROMOTED = "Promoted to Leads"


class AlreadyHandled(Exception):
    pass


def _clean(fields: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in fields.items() if v not in (None, "", [])}


def lead_fields_from_signal(raw_id: str, f: Dict[str, Any]) -> Dict[str, Any]:
    """The Make scenario's mapping, field for field, plus the back-link."""
    g = lambda key: f.get(R[key])  # noqa: E731
    evidence = (
        f"Official permit record {g('source_record_id') or ''}. Publicly listed contractor: "
        f"{g('contractor') or ''}. Parcel ID: {g('parcel_id') or ''}. Permit record: {g('source_url') or ''}"
    )
    work = " - ".join(x for x in (g("work_class"), g("description")) if x)
    return _clean({
        L["name"]: g("address"),
        L["address"]: g("address"),
        L["city"]: g("jurisdiction"),
        L["confidence"]: g("ai_confidence"),
        L["evidence"]: evidence,
        L["risk_flags"]: RISK_FLAGS,
        L["opportunity_type"]: g("ai_project_type"),
        L["estimated_job_value"]: g("ai_value"),
        L["ai_summary"]: g("ai_reasons"),
        L["permit_value"]: g("estimated_value"),
        L["permit_status"]: g("status_raw"),
        L["source_url"]: g("source_url"),
        L["source_category"]: "Permit",
        L["hunt_status"]: "Validated",
        L["external_id"]: g("signal_id"),
        L["recent_activity"]: True,
        L["contact_company"]: g("contractor"),
        L["enrichment_status"]: "Ready for research",
        L["why_matters"]: g("ai_reasons"),
        L["permit_event_date"]: g("event_date"),
        L["priority"]: g("tier"),
        L["lead_score"]: g("score"),
        L["qualified"]: True,
        L["permit_description"]: work,
        L["permit_number"]: g("source_record_id"),
        L["parcel_id"]: g("parcel_id"),
        L["local_service_area"]: True,
        L["status"]: "New",
        L["signal_found"]: g("description"),
        L["source"]: "Permit",
        L["next_action"]: g("ai_next_action"),
        L["raw_signals"]: [raw_id],
        L["needs_classification"]: True,
    })


def signal_dto(record: Dict[str, Any]) -> Dict[str, Any]:
    f = record.get("fields", {}) or {}
    g = lambda key: f.get(R[key])  # noqa: E731
    return {
        "id": record.get("id"),
        "created_time": record.get("createdTime"),
        "address": g("address"),
        "project_type": g("ai_project_type"),
        "work_class": g("work_class"),
        "description": g("description"),
        "contractor": g("contractor"),
        "ai_confidence": g("ai_confidence"),
        "service_fit": g("ai_service_fit"),
        "ai_value": g("ai_value"),
        "permit_value": g("estimated_value"),
        "score": g("score"),
        "tier": g("tier"),
        "why": g("ai_reasons"),
        "next_action": g("ai_next_action"),
        "source_url": g("source_url"),
        "permit_number": g("source_record_id"),
        "event_date": g("event_date"),
        "promotion_status": g("promotion_status"),
    }


def _rank(s: Dict[str, Any]) -> tuple:
    fit = 1 if (s.get("service_fit") or "").lower() == "high" else 0
    return (-fit, -(s.get("ai_confidence") or 0), -(s.get("score") or 0))


class PromotionService:
    CACHE_TTL = 60.0

    def __init__(self, api_key: str, base_id: str, leads_table: str):
        api = make_api(api_key)
        self._raw = api.table(base_id, RAW_SIGNALS_TABLE)
        self._leads = api.table(base_id, leads_table)
        self._lock = threading.Lock()
        self._cache: Optional[List[Dict[str, Any]]] = None
        self._cached_at = 0.0

    def waiting(self) -> List[Dict[str, Any]]:
        with self._lock:
            if self._cache is not None and time.time() - self._cached_at < self.CACHE_TTL:
                return list(self._cache)
            records = self._raw.all(formula=WAITING_FORMULA, fields=list(R.values()),
                                    use_field_ids=True)
            items = sorted((signal_dto(r) for r in records), key=_rank)
            self._cache, self._cached_at = items, time.time()
            return list(items)

    def _invalidate(self) -> None:
        with self._lock:
            self._cache = None

    def _fetch(self, raw_id: str) -> Dict[str, Any]:
        rec = self._raw.get(raw_id, use_field_ids=True)
        status = (rec.get("fields", {}) or {}).get(R["promotion_status"]) or ""
        if status == PROMOTED or status.startswith("Passed by Ryan") or status.startswith("Disqualified"):
            raise AlreadyHandled(f"This signal was already handled ({status}).")
        return rec

    def promote(self, raw_id: str) -> Dict[str, Any]:
        rec = self._fetch(raw_id)
        lead = self._leads.create(lead_fields_from_signal(raw_id, rec.get("fields", {}) or {}),
                                  typecast=True, use_field_ids=True)
        self._raw.update(raw_id, {R["promotion_status"]: PROMOTED}, use_field_ids=True)
        self._invalidate()
        log.info("Promoted raw signal %s to lead %s", raw_id, lead.get("id"))
        return {"lead_id": lead.get("id"), "signal_id": raw_id}

    def pass_signal(self, raw_id: str, reason_key: str, note: Optional[str] = None) -> Dict[str, Any]:
        reason = reason_for(reason_key)
        self._fetch(raw_id)
        note = (note or "").strip()
        status = f"Passed by Ryan: {reason['label']}" + (f" — {note[:120]}" if note else "")
        self._raw.update(raw_id, {R["promotion_status"]: status}, use_field_ids=True)
        self._invalidate()
        return {"signal_id": raw_id, "promotion_status": status}


_service: Optional[PromotionService] = None
_service_lock = threading.Lock()


def get_promotion_service() -> Optional[PromotionService]:
    """Lazy singleton; None when Airtable isn't configured (sample mode)."""
    global _service
    with _service_lock:
        if _service is not None:
            return _service
        api_key = os.environ.get("AIRTABLE_API_KEY")
        base_id = os.environ.get("AIRTABLE_BASE_ID")
        leads_table = os.environ.get("AIRTABLE_OPPORTUNITIES_TABLE") or "Leads"
        if os.environ.get("AIRTABLE_ENABLED", "").lower() != "true" or not (api_key and base_id):
            return None
        _service = PromotionService(api_key, base_id, leads_table)
        return _service
