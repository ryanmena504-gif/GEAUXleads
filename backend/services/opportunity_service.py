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
from services.airtable_service import build_airtable_service_from_env

log = logging.getLogger("bloodhound.service")


def _synthesize_governed(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Fill in plausible governed-layer values on SAMPLE records so the
    preview UI exercises the 3-list logic end-to-end when Airtable is not
    reachable. NEVER runs on real Airtable records — those go through
    airtable_service._record_to_opportunity() unchanged."""
    status = str(rec.get("status") or rec.get("status_raw") or "").lower()
    outreach_sent = bool(rec.get("flag_outreach_sent"))
    has_phone = bool(rec.get("phone") or rec.get("phone_alt"))
    has_email = bool(rec.get("email") or rec.get("email_alt"))
    priority = float(rec.get("priority_score") or 0)

    # Bucket by activity signals — this is a stand-in for what Make would set.
    if status in ("won", "lost", "disqualified"):
        queue = "All Projects"
        readiness = "Not Appropriate"
    elif outreach_sent or status in ("conversation started", "estimate requested", "estimate sent"):
        queue = "Contacted"
        readiness = "Contacted"
    elif has_phone and has_email and priority >= 60:
        queue = "Ready to Contact"
        readiness = "Ready"
    elif not has_phone and not has_email:
        queue = "All Projects"
        readiness = "Needs Public Contact"
    else:
        queue = "All Projects"
        readiness = "Needs Proof"

    rec.setdefault("current_queue", queue)
    rec.setdefault("contact_readiness", readiness)
    rec.setdefault("contact_state",
                   "Follow-Up Due" if queue == "Contacted" else
                   "Ready for first contact" if queue == "Ready to Contact" else
                   "Not classified")
    rec.setdefault("money_signal",
                   "High" if (rec.get("estimated_value") or 0) >= 100_000 else
                   "Medium" if (rec.get("estimated_value") or 0) >= 25_000 else
                   "Low")
    rec.setdefault("operator_activity",
                   "Paused" if status == "on hold" else "Active")
    rec.setdefault("premium_fit", "Strong" if rec.get("flag_premium") else "Standard")
    rec.setdefault("evidence_status", "Verified" if rec.get("flag_verified") else "Unverified")
    rec.setdefault("freshness",
                   "Current" if priority >= 70 else
                   "Aging" if priority >= 40 else
                   "Stale")
    rec.setdefault("governed_priority_score", int(priority) if priority else 20)
    rec.setdefault("score_basis",
                   "priority=" + str(int(priority)) + " · has_contact=" +
                   str(has_phone or has_email) + " · premium=" +
                   str(bool(rec.get("flag_premium"))))
    rec.setdefault("priority_explanation",
                   rec.get("recommendation_reason") or "No governed explanation on file.")
    rec.setdefault("current_recommendation",
                   rec.get("next_best_action") or rec.get("recommended_action") or "")
    if has_phone or has_email:
        rec.setdefault("public_contact_evidence",
                       "Public business channel on file: " +
                       (rec.get("email") or rec.get("phone") or ""))
    rec.setdefault("contact_verified_date", rec.get("last_reviewed"))
    rec.setdefault("project_fit_reason",
                   rec.get("evidence_summary") or rec.get("recommendation_reason") or "")
    rec.setdefault("last_classified_at", rec.get("created_time"))
    rec.setdefault("classification_version", "sample-v1")
    return rec

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
        self._data: Dict[str, Dict[str, Any]] = {
            o["id"]: _synthesize_governed(deepcopy(o)) for o in SAMPLE_OPPORTUNITIES
        }

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
        active = [o for o in self.all() if o.get("status") not in ("Won", "Lost", "Disqualified")]
        active.sort(key=lambda o: o.get("priority_score", 0), reverse=True)
        return active[:limit]

    def recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        items = list(self.all())
        items.sort(key=lambda o: o.get("created_time", ""), reverse=True)
        return items[:limit]

    def summary(self) -> Dict[str, Any]:
        all_ops = self.all()
        active = [o for o in all_ops if o.get("status") not in ("Won", "Lost", "Disqualified")]
        immediate = [o for o in active if o.get("daily_mission") in
                     ("Call Today", "Send Text", "Visit Property")]
        ready = [o for o in active if o.get("status") == "Ready"]
        needs_research = [o for o in active if o.get("status") == "Needs research"
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
        for o in self.all():
            if o.get("status") in ("Won", "Lost", "Disqualified"):
                continue
            mission = o.get("daily_mission")
            if mission in groups:
                groups[mission].append(o)
        for m in groups:
            groups[m].sort(key=lambda o: o.get("priority_score", 0), reverse=True)
        return groups

    def pipeline_counts(self) -> List[Dict[str, Any]]:
        counts = {s: 0 for s in PIPELINE_STATUSES}
        values = {s: 0.0 for s in PIPELINE_STATUSES}
        for o in self.all():
            s = o.get("status")
            if s in counts:
                counts[s] += 1
                values[s] += (o.get("estimated_value") or 0)
        return [
            {"status": s, "count": counts[s], "value": values[s]}
            for s in PIPELINE_STATUSES
        ]

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
