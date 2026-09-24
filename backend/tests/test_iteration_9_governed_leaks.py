"""Iteration 9 — verify governed-field leaks fixes + 3 new QA records."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")


@pytest.fixture(scope="module")
def all_ops():
    r = requests.get(f"{BASE_URL}/api/opportunities", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _list(data):
    if isinstance(data, list):
        return data
    for k in ("opportunities", "items", "results", "data"):
        if isinstance(data, dict) and isinstance(data.get(k), list):
            return data[k]
    raise AssertionError(f"unexpected shape: {type(data)}")


def test_total_18(all_ops):
    ops = _list(all_ops)
    assert len(ops) == 18, f"expected 18 records got {len(ops)}"


def test_bucket_distribution(all_ops):
    ops = _list(all_ops)
    ready = [o for o in ops if o.get("current_queue") == "Ready to Contact"]
    contacted = [o for o in ops if o.get("current_queue") == "Contacted"]
    all_p = [o for o in ops if o.get("current_queue") not in ("Ready to Contact", "Contacted")]
    assert len(ready) == 4, [o["id"] for o in ready]
    assert len(contacted) == 5, [o["id"] for o in contacted]
    assert len(all_p) == 9, [o["id"] for o in all_p]


@pytest.mark.parametrize("opp_id,expected", [
    ("opp_greige", {"current_queue": "Contacted", "contact_readiness": "Contacted",
                    "contact_state": "Follow-Up Due", "lane": "partner"}),
    ("opp_louisiana", {"current_queue": "All Projects", "contact_readiness": "Paused",
                       "governed_priority_score": 20, "lane": "partner"}),
    ("opp_sweeney", {"current_queue": "Ready to Contact", "contact_readiness": "Ready",
                     "governed_priority_score": 93, "lane": "partner"}),
])
def test_qa_records(opp_id, expected):
    r = requests.get(f"{BASE_URL}/api/opportunities/{opp_id}", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    for k, v in expected.items():
        assert data.get(k) == v, f"{opp_id}.{k}={data.get(k)} expected {v}"


def test_ready_ordering(all_ops):
    ops = _list(all_ops)
    ready = [o for o in ops if o.get("current_queue") == "Ready to Contact"]
    ready_sorted = sorted(ready, key=lambda o: -(o.get("governed_priority_score") or 0))
    ids = [o["id"] for o in ready_sorted]
    assert ids == ["opp_004", "opp_001", "opp_sweeney", "opp_002"], ids
