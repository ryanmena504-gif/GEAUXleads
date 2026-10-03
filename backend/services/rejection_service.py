"""
One-tap "pass" on a lead, with the reason the classifier learning loop needs.

Passing a lead writes three things through the existing write paths:
  • Status            → "Disqualified" (unless the lead is already closed)
  • Rejection reason  → the preset's select value
  • Activity Log      → "ISO | disqualified | <detail> — <note>"

Airtable adds a preset as a new Rejection reason option the first time it is
written (update_fields uses typecast). If the base refuses — e.g. the token
can't edit the schema — the write falls back to the closest legacy option so
the tap is never lost; the exact preset still lands in Activity Log.

Nothing here sends a message. Undo restores the previous status and clears
the reason.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from services.airtable_service import AirtableWriteError

log = logging.getLogger("bloodhound.rejection")

# key → select value written to Rejection reason, the longer wording shown on
# the button and written to Activity Log, and the legacy option to fall back to.
REJECTION_REASONS: List[Dict[str, str]] = [
    {"key": "wrong_trade", "label": "Wrong trade",
     "detail": "Wrong trade (roof, solar, HVAC, flooring, foundation…)", "fallback": "Wrong project type"},
    {"key": "no_bath_scope", "label": "No bathroom scope",
     "detail": "Whole-house / new construction / addition (no shower or bathroom scope)", "fallback": "Wrong project type"},
    {"key": "commercial", "label": "Commercial",
     "detail": "Commercial — not a home bathroom", "fallback": "Wrong project type"},
    {"key": "not_my_trade", "label": "Not my trade",
     "detail": "Not my trade (general handyman / odd jobs)", "fallback": "Wrong Fit"},
    {"key": "no_remodel_intent", "label": "No remodel intent",
     "detail": "Investor / LLC / property sale — no remodel intent", "fallback": "Wrong Fit"},
    {"key": "type_unknown", "label": "Project type unknown",
     "detail": "Project type unknown", "fallback": "Bad data"},
    {"key": "spam", "label": "Spam / contractor ad",
     "detail": "Contractor ad / spam", "fallback": "Bad data"},
    {"key": "duplicate", "label": "Duplicate",
     "detail": "Duplicate lead", "fallback": "Duplicate"},
]
_BY_KEY = {r["key"]: r for r in REJECTION_REASONS}

CLOSED_STATUSES = ("Won", "Lost", "Disqualified")
# Rejection reason values that are placeholders, not a decision.
_PLACEHOLDER_REASONS = {"", "pending"}


class UnknownReason(ValueError):
    pass


def reason_for(key: str) -> Dict[str, str]:
    r = _BY_KEY.get(key)
    if r is None:
        raise UnknownReason(f"Unknown reason '{key}'. Use one of: {', '.join(_BY_KEY)}")
    return r


def needs_reason(opp: Dict[str, Any]) -> bool:
    """A disqualified lead with no real Rejection reason on file."""
    if opp.get("status") != "Disqualified":
        return False
    outcome = opp.get("outcome")
    return not (isinstance(outcome, str) and outcome.strip().lower() not in _PLACEHOLDER_REASONS)


def backlog(svc, limit: int = 200) -> Dict[str, Any]:
    everything = svc.all()
    rows = [o for o in everything if needs_reason(o)]
    rows.sort(key=lambda o: (o.get("date_discovered") or o.get("created_time") or ""), reverse=True)
    disqualified = sum(1 for o in everything if o.get("status") == "Disqualified")
    return {"items": rows[:limit], "count": len(rows), "disqualified_total": disqualified}


def _write_reason(svc, opp_id: str, updates: Dict[str, Any], reason: Dict[str, str]) -> Dict[str, Any]:
    try:
        opp = svc.update_fields(opp_id, {**updates, "outcome": reason["label"]})
        return {"opp": opp, "written": reason["label"], "fell_back": False}
    except AirtableWriteError as e:
        if reason["fallback"] == reason["label"]:
            raise
        log.warning("Rejection reason '%s' refused (%s) — falling back to '%s'",
                    reason["label"], e, reason["fallback"])
        opp = svc.update_fields(opp_id, {**updates, "outcome": reason["fallback"]})
        return {"opp": opp, "written": reason["fallback"], "fell_back": True}


def pass_lead(svc, opp_id: str, reason_key: str, note: Optional[str] = None) -> Optional[Dict[str, Any]]:
    reason = reason_for(reason_key)
    opp = svc.get(opp_id)
    if not opp:
        return None
    previous_status = opp.get("status_raw") or opp.get("status")
    updates: Dict[str, Any] = {}
    if opp.get("status") not in CLOSED_STATUSES:
        updates["status"] = "Disqualified"

    result = _write_reason(svc, opp_id, updates, reason)

    note = (note or "").strip()
    entry = reason["detail"] + (f" — {note}" if note else "")
    activity_logged = True
    try:
        svc.add_activity(opp_id, "disqualified", entry)
    except AirtableWriteError as e:
        # The reason and status are saved; a missing journal line shouldn't
        # undo the decision.
        log.warning("Activity Log append failed for %s: %s", opp_id, e)
        activity_logged = False

    return {
        "opportunity": svc.get(opp_id) or result["opp"],
        "reason": reason["key"],
        "rejection_reason_written": result["written"],
        "fell_back": result["fell_back"],
        "status_changed": "status" in updates,
        "previous_status": previous_status,
        "activity_logged": activity_logged,
    }


def undo_pass(svc, opp_id: str, previous_status: Optional[str]) -> Optional[Dict[str, Any]]:
    opp = svc.get(opp_id)
    if not opp:
        return None
    updates: Dict[str, Any] = {"outcome": ""}
    if previous_status and previous_status != opp.get("status_raw"):
        updates["status"] = previous_status
    svc.update_fields(opp_id, updates)
    try:
        svc.add_activity(opp_id, "pass_undone", f"Pass undone — status back to {previous_status or 'unchanged'}")
    except AirtableWriteError as e:
        log.warning("Activity Log append failed for %s: %s", opp_id, e)
    return svc.get(opp_id)
