"""Promote / pass AI-approved Raw Signals from the app."""
from __future__ import annotations

import threading

import pytest

from services.promotion_service import (
    PROMOTED, AlreadyHandled, L, PromotionService, R, lead_fields_from_signal, signal_dto,
)


class FakeTable:
    def __init__(self, rows=None):
        self.rows = rows or {}
        self.created, self.updated = [], []

    def all(self, **kw):
        return [{"id": k, "createdTime": "2026-09-10T00:00:00Z", "fields": v} for k, v in self.rows.items()]

    def get(self, rid, **kw):
        return {"id": rid, "fields": self.rows[rid]}

    def create(self, fields, **kw):
        self.created.append((fields, kw))
        return {"id": "recNEWLEAD", "fields": fields}

    def update(self, rid, fields, **kw):
        self.updated.append((rid, fields))
        self.rows[rid].update(fields)
        return {"id": rid, "fields": self.rows[rid]}


SIGNAL = {
    R["signal_id"]: "nola_blds_permits|26-24345-PLMB",
    R["source_record_id"]: "26-24345-PLMB",
    R["address"]: "3216 Potomac St, New Orleans, LA 70114",
    R["jurisdiction"]: "New Orleans",
    R["work_class"]: "Plumbing Permit",
    R["description"]: "Install plumbing for 2.5 baths",
    R["contractor"]: "Ali Reza Mesbah",
    R["source_url"]: "https://data.nola.gov/x",
    R["ai_confidence"]: 85,
    R["ai_service_fit"]: "high",
    R["ai_project_type"]: "bathroom plumbing install for 2.5 baths",
    R["ai_value"]: 0,
    R["score"]: 50,
    R["tier"]: "Warm",
    R["ai_decision"]: "ready_for_campaign_review",
    R["promotion_status"]: "AI Decided",
}


def make_svc(rows):
    svc = PromotionService.__new__(PromotionService)
    svc._raw = FakeTable(rows)
    svc._leads = FakeTable()
    svc._lock = threading.Lock()
    svc._cache = None
    svc._cached_at = 0.0
    return svc


def test_mapping_mirrors_the_make_scenario_and_links_back():
    f = lead_fields_from_signal("recRAW", SIGNAL)
    assert f[L["name"]] == f[L["address"]] == "3216 Potomac St, New Orleans, LA 70114"
    assert f[L["status"]] == "New" and f[L["source"]] == "Permit"
    assert f[L["permit_number"]] == "26-24345-PLMB"
    assert f[L["permit_description"]] == "Plumbing Permit - Install plumbing for 2.5 baths"
    assert f[L["raw_signals"]] == ["recRAW"]
    assert f[L["needs_classification"]] is True
    assert f[L["estimated_job_value"]] == 0                 # zero kept, not dropped


def test_promote_creates_lead_and_marks_signal():
    svc = make_svc({"recRAW": dict(SIGNAL)})
    out = svc.promote("recRAW")
    assert out["lead_id"] == "recNEWLEAD"
    fields, kw = svc._leads.created[0]
    assert kw == {"typecast": True, "use_field_ids": True}
    assert svc._raw.rows["recRAW"][R["promotion_status"]] == PROMOTED


def test_cannot_promote_twice():
    svc = make_svc({"recRAW": dict(SIGNAL)})
    svc.promote("recRAW")
    with pytest.raises(AlreadyHandled):
        svc.promote("recRAW")
    assert len(svc._leads.created) == 1


def test_pass_records_reason_and_blocks_promotion():
    svc = make_svc({"recRAW": dict(SIGNAL)})
    out = svc.pass_signal("recRAW", "wrong_trade", "plumbing only")
    assert out["promotion_status"] == "Passed by Ryan: Wrong trade — plumbing only"
    with pytest.raises(AlreadyHandled):
        svc.promote("recRAW")


def test_waiting_ranks_high_fit_and_confidence_first():
    weak = dict(SIGNAL, **{R["ai_service_fit"]: "medium", R["ai_confidence"]: 90})
    strong = dict(SIGNAL, **{R["ai_service_fit"]: "high", R["ai_confidence"]: 80})
    svc = make_svc({"recWEAK": weak, "recSTRONG": strong})
    assert [s["id"] for s in svc.waiting()] == ["recSTRONG", "recWEAK"]
    assert signal_dto({"id": "x", "fields": SIGNAL})["permit_number"] == "26-24345-PLMB"
