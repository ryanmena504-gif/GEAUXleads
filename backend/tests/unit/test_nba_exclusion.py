"""Offline tests for NBA exclusion + Hunt gating.

No Airtable connection — LeadsAirtableService is built with __new__ and a
fake in-memory table.
"""
from __future__ import annotations

import threading

import pytest

from services.leads_service import LEADS_FIELD_MAP, LeadsAirtableService


class FakeTable:
    def __init__(self, rows):
        self.rows = rows
        self.writes = []

    def all(self):
        return [
            {"id": rid, "createdTime": "2026-07-01T00:00:00.000Z", "fields": dict(f)}
            for rid, f in self.rows.items()
        ]

    def update(self, record_id, fields):
        self.writes.append((record_id, dict(fields)))
        self.rows[record_id].update(fields)
        return {"id": record_id, "fields": self.rows[record_id]}


BASE = {
    "Leads Name": "Ashby Residence",
    "Next action": "Call about the Prytania roof permit",
    "Status": "New",
    "Outreach status": "Not sent",
}


def make_service(rows):
    svc = LeadsAirtableService.__new__(LeadsAirtableService)
    svc._base_id = "appTEST"
    svc._table_name = "Leads"
    svc._table_id = "tblTEST"
    svc._table = FakeTable(rows)
    svc._cache_ttl = 0.0
    svc._lock = threading.Lock()
    svc._cache = {}
    svc._last_refresh = 0.0
    svc._field_map = dict(LEADS_FIELD_MAP)
    svc._skipped = set()
    svc._held = set()
    svc._approvals = {}
    return svc


def test_not_sent_is_still_eligible_for_nba():
    """Regression: substring 'sent' must not exclude 'Not sent'."""
    svc = make_service({"rec1": dict(BASE)})
    pick = svc.pick_next_best_action()
    assert pick is not None
    assert pick["id"] == "rec1"


def test_hunt_rejected_never_surfaces_as_nba():
    svc = make_service({"rec1": {**BASE, "Hunt status": "Rejected"}})
    assert svc.pick_next_best_action() is None
    assert svc.queue_stats()["eligible"] == 0


def test_hunt_paused_never_surfaces_as_nba_after_restart():
    """Hold writes Hunt status=Paused; exclusion must not depend only on session set."""
    svc = make_service({"rec1": {**BASE, "Hunt status": "Paused"}})
    assert svc.pick_next_best_action() is None


def test_outreach_sent_checkbox_excludes_from_nba():
    svc = make_service({"rec1": {**BASE, "Outreach sent": True}})
    assert svc.pick_next_best_action() is None


def test_sent_outreach_status_excludes_but_not_not_sent():
    svc = make_service({
        "recFresh": dict(BASE),
        "recSent": {**BASE, "Leads Name": "Already contacted", "Outreach status": "Sent"},
    })
    pick = svc.pick_next_best_action()
    assert pick is not None
    assert pick["id"] == "recFresh"
    assert svc.queue_stats()["eligible"] == 1


def test_skeleton_rows_stay_excluded():
    svc = make_service({"recEmpty": {"Leads Name": None, "Next action": None}})
    assert svc.pick_next_best_action() is None
