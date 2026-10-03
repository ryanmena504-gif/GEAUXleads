"""One-tap pass: status, Rejection reason, Activity Log, fallback and undo."""
from __future__ import annotations

import pytest

from services.airtable_service import AirtableWriteError
from services.rejection_service import (
    REJECTION_REASONS, UnknownReason, backlog, needs_reason, pass_lead, undo_pass,
)


class FakeSvc:
    """Mimics the Airtable service write surface, including typecast refusal."""

    def __init__(self, rows, refuse_new_options=False, activity_fails=False):
        self.rows = {r["id"]: dict(r) for r in rows}
        self.refuse = refuse_new_options
        self.activity_fails = activity_fails
        self.legacy = {"Wrong project type", "Wrong Fit", "Bad data", "Duplicate", "Pending", ""}
        self.activity = []

    def all(self):
        return list(self.rows.values())

    def get(self, opp_id):
        return self.rows.get(opp_id)

    def update_fields(self, opp_id, updates):
        if self.refuse and updates.get("outcome") not in self.legacy:
            raise AirtableWriteError("INVALID_MULTIPLE_CHOICE_OPTIONS", 422)
        row = self.rows[opp_id]
        if "status" in updates:
            row["status"] = row["status_raw"] = updates["status"]
        if "outcome" in updates:
            row["outcome"] = updates["outcome"] or None
        return row

    def add_activity(self, opp_id, type_, note):
        if self.activity_fails:
            raise AirtableWriteError("Activity Log missing", 422)
        self.activity.append((opp_id, type_, note))
        return self.rows[opp_id]


def lead(**kw):
    base = {"id": "rec1", "name": "Lead", "status": "New", "status_raw": "New", "outcome": None}
    return {**base, **kw}


def test_pass_disqualifies_records_reason_and_journals():
    svc = FakeSvc([lead()])
    r = pass_lead(svc, "rec1", "wrong_trade", note="roof only")
    assert svc.rows["rec1"]["status"] == "Disqualified"
    assert svc.rows["rec1"]["outcome"] == "Wrong trade"
    assert r["fell_back"] is False and r["status_changed"] is True
    assert r["previous_status"] == "New"
    assert svc.activity == [("rec1", "disqualified",
                             "Wrong trade (roof, solar, HVAC, flooring, foundation…) — roof only")]


def test_refused_new_option_falls_back_to_legacy_option():
    svc = FakeSvc([lead()], refuse_new_options=True)
    r = pass_lead(svc, "rec1", "commercial")
    assert r["fell_back"] is True
    assert svc.rows["rec1"]["outcome"] == "Wrong project type"
    assert "Commercial" in svc.activity[0][2]       # exact preset still journaled


def test_backfill_on_already_disqualified_lead_keeps_status():
    svc = FakeSvc([lead(status="Disqualified", status_raw="Disqualified")])
    r = pass_lead(svc, "rec1", "duplicate")
    assert r["status_changed"] is False
    assert svc.rows["rec1"]["outcome"] == "Duplicate"


def test_activity_log_failure_does_not_lose_the_decision():
    svc = FakeSvc([lead()], activity_fails=True)
    r = pass_lead(svc, "rec1", "spam")
    assert r["activity_logged"] is False
    assert svc.rows["rec1"]["outcome"] == "Spam / contractor ad"


def test_unknown_reason_is_refused():
    with pytest.raises(UnknownReason):
        pass_lead(FakeSvc([lead()]), "rec1", "because")


def test_missing_lead_returns_none():
    assert pass_lead(FakeSvc([]), "nope", "spam") is None


def test_undo_restores_status_and_clears_reason():
    svc = FakeSvc([lead(status="Conversation started", status_raw="Conversation started")])
    r = pass_lead(svc, "rec1", "not_my_trade")
    undo_pass(svc, "rec1", r["previous_status"])
    assert svc.rows["rec1"]["status"] == "Conversation started"
    assert svc.rows["rec1"]["outcome"] is None


def test_backlog_counts_blank_and_pending_reasons_only():
    svc = FakeSvc([
        lead(id="a", status="Disqualified", outcome=None),
        lead(id="b", status="Disqualified", outcome="Pending"),
        lead(id="c", status="Disqualified", outcome="Wrong trade"),
        lead(id="d", status="New", outcome=None),
    ])
    out = backlog(svc)
    assert {o["id"] for o in out["items"]} == {"a", "b"}
    assert out["count"] == 2 and out["disqualified_total"] == 3
    assert needs_reason({"status": "New"}) is False


def test_reason_keys_are_unique_and_every_fallback_is_a_legacy_option():
    keys = [r["key"] for r in REJECTION_REASONS]
    assert len(keys) == len(set(keys))
    legacy = {"Wrong project type", "Wrong Fit", "Bad data", "Duplicate"}
    assert all(r["fallback"] in legacy for r in REJECTION_REASONS)
