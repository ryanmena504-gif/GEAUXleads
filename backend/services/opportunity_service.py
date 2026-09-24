"""
Opportunity data access layer.

This layer keeps the API surface stable while allowing the underlying data
source to change. Today it serves rich sample data. When Airtable env vars
are configured, `get_opportunity_service()` will return an AirtableOpportunityService
instead. No UI code needs to change.
"""
import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from copy import deepcopy

from data.sample_opportunities import SAMPLE_OPPORTUNITIES
from services import aggregations, dedupe
from services.airtable_service import build_airtable_service_from_env

log = logging.getLogger("bloodhound.service")


# The 17 governed fields owned by Airtable + Make. The sample fixtures set
# these explicitly; we only ensure the KEY exists (None when unset) so the
# API DTO shape is stable across records. We never invent a governed value.
GOVERNED_KEYS = (
    "current_queue",
    "contact_readiness",
    "contact_state",
    "money_signal",
    "operator_activity",
    "premium_fit",
    "evidence_status",
    "freshness",
    "governed_priority_score",
    "score_basis",
    "priority_explanation",
    "current_recommendation",
    "public_contact_evidence",
    "contact_verified_date",
    "project_fit_reason",
    "last_classified_at",
    "classification_version",
)


# The sample fixtures now carry the 17 governed fields verbatim, so the
# service layer never synthesises, infers, or overrides governed state.
# There is intentionally NO helper to backfill governed values — if a fixture
# omits `current_queue`, that record falls into All Projects, exactly as it
# would in production when Make hasn't classified a row yet.

# Populated by get_opportunity_service() when Airtable init fails, so
# /api/config can surface the exact reason (e.g. 401 Unauthorized) without
# forcing the operator to dig through server logs.
_last_init_error: Optional[str] = None


def get_last_init_error() -> Optional[str]:
    return _last_init_error


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


class SampleOpportunityService:
    backend_name = "sample"

    def __init__(self):
        self._data: Dict[str, Dict[str, Any]] = {}
        for o in SAMPLE_OPPORTUNITIES:
            rec = deepcopy(o)
            # Guarantee every governed key exists in the DTO (None when
            # unset in the fixture). This mirrors how the Airtable service
            # defaults unmapped keys — it does NOT invent a governed value.
            for k in GOVERNED_KEYS:
                rec.setdefault(k, None)
            self._data[rec["id"]] = rec

    def cache_status(self) -> Dict[str, Any]:
        # Sample data lives in-process forever; report as fresh.
        return {
            "backend": self.backend_name,
            "count": len(self._data),
            "last_refresh": datetime.now(timezone.utc).isoformat(),
            "age_seconds": 0,
            "ttl_seconds": None,
            "next_refresh_in": None,
            "is_stale": False,
            "is_refreshing": False,
            "last_error": None,
            "last_error_at": None,
            "consecutive_failures": 0,
        }

    def force_refresh(self) -> Dict[str, Any]:
        return self.cache_status()

    # ---------- reads ----------
    def all(self) -> List[Dict[str, Any]]:
        return list(self._data.values())

    def count(self) -> int:
        return len(self._data)

    def get(self, opp_id: str) -> Optional[Dict[str, Any]]:
        return self._data.get(opp_id)

    def list(self, source=None, status=None, priority_band=None,
             daily_mission=None, project_type=None, min_score=None,
             q=None, lane=None, sort=None) -> List[Dict[str, Any]]:
        results = self.all()
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
            results = [o for o in results if (o.get("priority_score") or 0) >= float(min_score)]
        if q:
            ql = q.lower()
            def match(o):
                blob = " ".join([
                    str(o.get("name", "")),
                    str(o.get("project_address", "")),
                    str(o.get("decision_maker", "")),
                    str(o.get("permit_number", "")),
                    str(o.get("project_type", "")),
                ]).lower()
                return ql in blob
            results = [o for o in results if match(o)]
        # sort by score desc
        results.sort(key=lambda o: o.get("priority_score", 0), reverse=True)
        return results

    def top(self, limit: int = 10) -> List[Dict[str, Any]]:
        return aggregations.top(self.all(), limit=limit)

    def recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        return aggregations.recent(self.all(), limit=limit)

    def summary(self) -> Dict[str, Any]:
        return aggregations.summary(self.all())

    def group_by_mission(self) -> Dict[str, List[Dict[str, Any]]]:
        return aggregations.group_by_mission(self.all())

    def pipeline_counts(self) -> List[Dict[str, Any]]:
        return aggregations.pipeline_counts(self.all())

    def duplicates_report(self) -> Dict[str, Any]:
        return dedupe.duplicate_report(self._duplicate_index)

    # ---------- writes ----------
    def update_status(self, opp_id: str, status: str) -> Optional[Dict[str, Any]]:
        opp = self._data.get(opp_id)
        if not opp:
            return None
        prev = opp.get("status")
        opp["status"] = status
        self._append_activity(opp, "status_change",
                              f"Status changed from {prev} to {status}")
        return opp

    def update_mission(self, opp_id: str, mission: str) -> Optional[Dict[str, Any]]:
        opp = self._data.get(opp_id)
        if not opp:
            return None
        opp["daily_mission"] = mission
        self._append_activity(opp, "mission_change", f"Mission set to {mission}")
        return opp

    def add_activity(self, opp_id: str, type_: str, note: Optional[str]) -> Optional[Dict[str, Any]]:
        opp = self._data.get(opp_id)
        if not opp:
            return None
        self._append_activity(opp, type_, note)
        return opp

    def update_fields(self, opp_id: str, updates_by_snake: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Sample-data equivalent of the Airtable write method used in tests."""
        opp = self._data.get(opp_id)
        if not opp:
            return None
        for key, value in updates_by_snake.items():
            if key == "ryans_decision":
                opp["ryans_decision"] = value
            elif key == "outcome":
                opp["outcome"] = value
            elif key == "next_follow_up":
                opp["next_follow_up"] = value
            elif key == "status":
                self.update_status(opp_id, value)
            else:
                opp[key] = value
        return opp

    def _append_activity(self, opp: Dict[str, Any], type_: str, note: Optional[str]):
        timeline = opp.setdefault("activity_timeline", [])
        timeline.insert(0, {
            "type": type_,
            "note": note or "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


_service_singleton = None


def get_opportunity_service():
    """Return the active opportunity service.
    Prefers a live Airtable-backed service when AIRTABLE_ENABLED=true and
    credentials are present; otherwise falls back to sample data.
    """
    global _service_singleton, _last_init_error
    if _service_singleton is None:
        try:
            airtable = build_airtable_service_from_env()
        except Exception as e:  # pragma: no cover — defensive
            airtable = None
            _last_init_error = f"{type(e).__name__}: {str(e)[:240]}"
        if airtable is not None:
            log.info("Opportunity service: using live Airtable backend")
            _service_singleton = airtable
            _last_init_error = None
        else:
            # Airtable was configured but init returned None — capture the
            # provider's error message from the airtable_service log module
            # so /api/config can show it.
            if _last_init_error is None and os.environ.get("AIRTABLE_ENABLED", "").lower() == "true":
                from services.airtable_service import get_last_build_error
                _last_init_error = get_last_build_error()
            log.info("Opportunity service: using in-memory sample backend")
            _service_singleton = SampleOpportunityService()
    return _service_singleton


def reset_opportunity_service():
    """Force the next call to rebuild the service. Handy after env changes."""
    global _service_singleton
    _service_singleton = None
