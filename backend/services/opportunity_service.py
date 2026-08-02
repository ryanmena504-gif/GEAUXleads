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

# Owned by services.aggregations so the sample and Airtable backends cannot
# drift apart again. Re-exported for existing importers.
PIPELINE_STATUSES = aggregations.PIPELINE_STATUSES
ACTIONABLE_MISSIONS = aggregations.ACTIONABLE_MISSIONS


class SampleOpportunityService:
    backend_name = "sample"

    def __init__(self):
        self._data: Dict[str, Dict[str, Any]] = {
            o["id"]: deepcopy(o) for o in SAMPLE_OPPORTUNITIES
        }
        # Same dedupe pass the live backend runs, so duplicate suppression is
        # exercised on sample data too rather than only in production.
        self._duplicate_index = dedupe.annotate(list(self._data.values()))

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
             q=None, include_duplicates: bool = False) -> List[Dict[str, Any]]:
        return aggregations.filter_records(
            self.all(), source=source, status=status,
            priority_band=priority_band, daily_mission=daily_mission,
            project_type=project_type, min_score=min_score, q=q,
            include_duplicates=include_duplicates,
        )

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
    global _service_singleton
    if _service_singleton is None:
        airtable = build_airtable_service_from_env()
        if airtable is not None:
            log.info("Opportunity service: using live Airtable backend")
            _service_singleton = airtable
        else:
            log.info("Opportunity service: using in-memory sample backend")
            _service_singleton = SampleOpportunityService()
    return _service_singleton


def reset_opportunity_service():
    """Force the next call to rebuild the service. Handy after env changes."""
    global _service_singleton
    _service_singleton = None
