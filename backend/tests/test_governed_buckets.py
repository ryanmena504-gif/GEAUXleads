"""Strict 17-governed-field enforcement tests for /api/opportunities.

Covers:
- Every record has all 17 governed KEYS (values may be None).
- Bucket distribution: 3 Ready to Contact / 4 Contacted / 8 All Projects.
- Per-record current_queue + contact_readiness expected values.
- No legacy fallback: high-priority-score records with phone/email but
  current_queue == "All Projects" stay in All Projects.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")

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


@pytest.fixture(scope="module")
def opps():
    r = requests.get(f"{BASE_URL}/api/opportunities", timeout=15)
    assert r.status_code == 200, f"GET /api/opportunities failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    # Accept either list or {opportunities: [...]}
    if isinstance(data, dict) and "opportunities" in data:
        data = data["opportunities"]
    assert isinstance(data, list)
    return data


def test_returns_records(opps):
    assert len(opps) > 0, "Expected at least one opportunity record"


def test_every_record_has_17_governed_keys(opps):
    missing = {}
    for o in opps:
        m = [k for k in GOVERNED_KEYS if k not in o]
        if m:
            missing[o.get("id")] = m
    assert not missing, f"Records missing governed keys: {missing}"


def test_bucket_distribution(opps):
    counts = {"Ready to Contact": 0, "Contacted": 0, "All Projects": 0}
    others = []
    for o in opps:
        q = o.get("current_queue")
        if q in counts:
            counts[q] += 1
        else:
            others.append((o.get("id"), q))
    assert counts["Ready to Contact"] == 3, f"Ready to Contact count mismatch: {counts}"
    assert counts["Contacted"] == 4, f"Contacted count mismatch: {counts}"
    assert counts["All Projects"] == 8, f"All Projects count mismatch: {counts}"
    assert not others, f"Unexpected current_queue values: {others}"


@pytest.mark.parametrize("opp_id", ["opp_001", "opp_002", "opp_004"])
def test_ready_records(opp_id):
    r = requests.get(f"{BASE_URL}/api/opportunities/{opp_id}", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["current_queue"] == "Ready to Contact"
    assert d["contact_readiness"] == "Ready"


@pytest.mark.parametrize("opp_id", ["opp_008", "opp_009", "opp_011", "opp_015"])
def test_contacted_records(opp_id):
    r = requests.get(f"{BASE_URL}/api/opportunities/{opp_id}", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["current_queue"] == "Contacted"
    assert d["contact_readiness"] == "Contacted"


def test_opp_005_paused_via_contact_readiness():
    r = requests.get(f"{BASE_URL}/api/opportunities/opp_005", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["contact_readiness"] == "Paused"
    assert d["current_queue"] == "All Projects"


def test_no_legacy_fallback_opp_003_and_012(opps):
    ids = {o["id"]: o for o in opps}
    for oid in ("opp_003", "opp_012"):
        assert oid in ids, f"{oid} missing"
        assert ids[oid]["current_queue"] == "All Projects", (
            f"{oid} must stay in All Projects, got {ids[oid]['current_queue']}"
        )


def test_ready_ordering_by_governed_score(opps):
    ready = [o for o in opps if o.get("current_queue") == "Ready to Contact"]
    ready_sorted = sorted(ready, key=lambda o: o.get("governed_priority_score") or -1, reverse=True)
    ids = [o["id"] for o in ready_sorted]
    assert ids == ["opp_004", "opp_001", "opp_002"], f"Order: {ids}"
    assert ready_sorted[0]["governed_priority_score"] == 96
    assert ready_sorted[1]["governed_priority_score"] == 94
    assert ready_sorted[2]["governed_priority_score"] == 88
