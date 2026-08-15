"""Offline tests: sample list must never 500 when sort= is passed."""
from __future__ import annotations

from services.opportunity_service import (
    SampleOpportunityService,
    get_opportunity_service,
    reset_opportunity_service,
)


def test_sample_list_accepts_sort_kwarg():
    svc = SampleOpportunityService()
    rows = svc.list(sort="lead_score")
    assert isinstance(rows, list)
    assert len(rows) == 15


def test_sample_list_accepts_unknown_kwargs():
    svc = SampleOpportunityService()
    rows = svc.list(sort="freshness", future_flag=True)
    assert len(rows) == 15


def test_sample_backend_via_env(monkeypatch):
    monkeypatch.setenv("AIRTABLE_ENABLED", "false")
    reset_opportunity_service()
    svc = get_opportunity_service()
    assert svc.backend_name == "sample"
    assert len(svc.list(sort="lead_score")) == 15
