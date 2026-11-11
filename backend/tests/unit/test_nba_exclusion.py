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
    "recommended action": "Call about the Prytania shower permit",
    "Status": "New",
    "Outreach status": "Not sent",
    "Contact phone": "504-231-8890",
    "Source URL": "https://permits.nola.gov/ashby",
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


def test_sent_by_ryan_and_replied_are_whole_values_not_substrings():
    """'Sent by Ryan' and 'Replied' drop out. Values that merely contain
    the letters s-e-n-t ('Not sent', 'Consent') stay eligible."""
    svc = make_service({
        "recFresh": dict(BASE),
        "recRyan": {**BASE, "Leads Name": "Already sent by Ryan",
                    "Contact phone": "504-301-7788", "Outreach status": "Sent by Ryan"},
        "recReplied": {**BASE, "Leads Name": "They replied",
                       "Contact phone": "504-301-7799", "Outreach status": "Replied"},
        "recConsent": {**BASE, "Leads Name": "Consent pending",
                       "Contact phone": "504-301-7700", "Outreach status": "Consent",
                       "Lead score": 10},
    })
    pick = svc.pick_next_best_action()
    assert pick is not None
    assert pick["id"] in {"recFresh", "recConsent"}
    assert svc.queue_stats()["eligible"] == 2


def test_lookup_list_sent_is_still_excluded():
    svc = make_service({
        "recSent": {**BASE, "Outreach status": ["Sent"]},
    })
    assert svc.pick_next_best_action() is None


def test_contact_ready_requires_phone_or_email_and_source_url():
    email_only = {**BASE, "Contact phone": None, "Contact email": "office@greigehome.com"}
    no_url = {**BASE, "Source URL": None, "Contact phone": "504-301-7788"}
    bad_phone = {**BASE, "Contact phone": "555-555-5555", "Contact email": None,
                 "Leads Name": "Placeholder phone"}
    svc = make_service({
        "recEmail": email_only,
        "recNoUrl": no_url,
        "recBadPhone": bad_phone,
    })
    pick = svc.pick_next_best_action()
    assert pick is not None
    assert pick["id"] == "recEmail"
    assert svc.queue_stats()["eligible"] == 1


def test_null_fields_and_mixed_date_types_do_not_crash_the_sort():
    """Live rows mix null decision-makers, text scores, and lookup dates."""
    svc = make_service({
        "recLow": {
            **BASE,
            "Leads Name": "Low score",
            "Contact name": None,
            "Contact phone": "504-301-7788",
            "Lead score": "12",
            "Date discovered": ["2026-01-02"],
            "Official project value": "Not public",
        },
        "recHigh": {
            **BASE,
            "Leads Name": "High score",
            "Contact name": None,
            "Contact phone": "504-301-7799",
            "Lead score": 80,
            "Date discovered": "2026-03-01",
            "Official project value": None,
        },
    })
    pick = svc.pick_next_best_action()
    assert pick is not None
    assert pick["id"] == "recHigh"


def test_leads_service_getter_does_not_crash_when_disabled(monkeypatch):
    """Regression: reading an unset _singleton raised NameError and HTTP 500."""
    from services.leads_service import get_leads_service, reset_leads_service

    monkeypatch.setenv("AIRTABLE_ENABLED", "false")
    reset_leads_service()
    assert get_leads_service() is None
    assert get_leads_service() is None


def test_next_best_action_route_returns_json_pick(monkeypatch):
    """The route must answer 200 JSON, not Starlette's text/plain 500."""
    from fastapi.testclient import TestClient

    import server

    svc = make_service({"rec1": {**BASE, "Lead score": 80}})
    monkeypatch.setattr(server, "get_leads_service", lambda: svc)
    monkeypatch.setenv("APP_PASSWORD", "test-password")
    with TestClient(server.app) as client:
        response = client.get(
            "/api/leads/next-best-action",
            headers={"X-App-Password": "test-password"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["lead"]["id"] == "rec1"
    assert body["lead"]["name"] == "Ashby Residence"
    assert body["lead"]["next_action"]
    assert body["queue"]["eligible"] == 1
    assert body["queue"]["total"] == 1
