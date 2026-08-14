"""Bloodhound Intelligence API tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hound-priorities.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- health / config ----------
def test_health(client):
    r = client.get(f"{API}/health", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["backend"] == "sample"
    assert d["count"] == 15


def test_config(client):
    r = client.get(f"{API}/config", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["airtable_configured"] is False
    assert d["backend"] == "sample"


# ---------- list + filters ----------
def test_list_all(client):
    r = client.get(f"{API}/opportunities", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 15


@pytest.mark.parametrize("params", [
    {"source": "permit"},
    {"status": "Ready"},
    {"priority_band": "A"},
    {"daily_mission": "Call Today"},
    {"min_score": 80},
    {"q": "chartres"},
])
def test_list_filters(client, params):
    r = client.get(f"{API}/opportunities", params=params, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if "source" in params:
        assert all(o["source"] == "permit" for o in data)
    if "status" in params:
        assert all(o["status"] == "Ready" for o in data)
    if "priority_band" in params:
        assert all(o["priority_band"] == "A" for o in data)
    if "daily_mission" in params:
        assert all(o["daily_mission"] == "Call Today" for o in data)
    if "min_score" in params:
        assert all(o.get("priority_score", 0) >= 80 for o in data)
    if params.get("q") == "chartres":
        assert len(data) >= 1
        assert any("chartres" in (o.get("project_address", "").lower()) for o in data)


# ---------- summary ----------
def test_summary(client):
    r = client.get(f"{API}/opportunities/summary", timeout=15)
    assert r.status_code == 200
    d = r.json()
    for k in ["new_opportunities", "immediate_action", "ready_to_contact",
              "needs_research", "total_pipeline_value", "active_count", "total_count"]:
        assert k in d
    assert d["total_count"] == 15


# ---------- missions ----------
def test_missions(client):
    r = client.get(f"{API}/opportunities/missions", timeout=15)
    assert r.status_code == 200
    d = r.json()
    expected = {"Call Today", "Send Text", "Send Email", "Research First",
                "Visit Property", "Prepare Estimate", "Ask for Referral",
                "Follow Up", "Wait"}
    assert expected.issubset(set(d.keys()))
    # excludes Won/Lost/Disqualified
    for m, items in d.items():
        for o in items:
            assert o["status"] not in ("Won", "Lost", "Disqualified")


# ---------- pipeline ----------
def test_pipeline(client):
    r = client.get(f"{API}/opportunities/pipeline", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d, list)
    assert len(d) == 9
    for stage in d:
        assert "status" in stage
        assert "count" in stage
        assert "value" in stage


# ---------- top / recent ----------
def test_top(client):
    r = client.get(f"{API}/opportunities/top", params={"limit": 6}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert len(d) <= 6
    scores = [o.get("priority_score", 0) for o in d]
    assert scores == sorted(scores, reverse=True)
    for o in d:
        assert o["status"] not in ("Won", "Lost", "Disqualified")


def test_recent(client):
    r = client.get(f"{API}/opportunities/recent", params={"limit": 6}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert len(d) <= 6
    times = [o.get("created_time", "") for o in d]
    assert times == sorted(times, reverse=True)


# ---------- detail ----------
def test_get_opp(client):
    r = client.get(f"{API}/opportunities/opp_001", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["id"] == "opp_001"
    assert "marigny" in d.get("name", "").lower() or "shotgun" in d.get("name", "").lower()


def test_get_missing(client):
    r = client.get(f"{API}/opportunities/missing_id", timeout=15)
    assert r.status_code == 404


# ---------- writes ----------
def test_patch_status(client):
    r = client.patch(f"{API}/opportunities/opp_003/status", json={"status": "Ready"}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "Ready"
    timeline = d.get("activity_timeline", [])
    assert any(e.get("type") == "status_change" for e in timeline)


def test_patch_mission(client):
    r = client.patch(f"{API}/opportunities/opp_005/mission", json={"daily_mission": "Follow Up"}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["daily_mission"] == "Follow Up"
    timeline = d.get("activity_timeline", [])
    assert any(e.get("type") == "mission_change" for e in timeline)


def test_post_activity(client):
    r = client.post(f"{API}/opportunities/opp_001/activity",
                    json={"type": "call", "note": "Left voicemail"}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    timeline = d.get("activity_timeline", [])
    assert len(timeline) > 0
    assert timeline[0]["type"] == "call"
    assert timeline[0]["note"] == "Left voicemail"


# ---------- iteration 2: /schema, /admin/reload, PATCH /fields ----------
def test_schema_sample_backend(client):
    r = client.get(f"{API}/schema", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["backend"] == "sample"
    assert "note" in d
    assert "sample" in d["note"].lower()


def test_admin_reload(client):
    r = client.post(f"{API}/admin/reload", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["backend"] == "sample"
    # subsequent health still works
    r2 = client.get(f"{API}/health", timeout=15)
    assert r2.status_code == 200
    assert r2.json()["count"] == 15


def test_config_airtable_enabled_false(client):
    r = client.get(f"{API}/config", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["airtable_enabled"] is False
    assert d["airtable_configured"] is False


def test_patch_fields_all_four(client):
    payload = {
        "ryans_decision": "Pursue",
        "outcome": "Pending",
        "next_follow_up": "2026-03-01",
        "status": "Conversation started",
    }
    r = client.patch(f"{API}/opportunities/opp_004/fields", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ryans_decision"] == "Pursue"
    assert d["outcome"] == "Pending"
    assert d["next_follow_up"] == "2026-03-01"
    assert d["status"] == "Conversation started"

    # verify persistence via GET
    r2 = client.get(f"{API}/opportunities/opp_004", timeout=15)
    assert r2.status_code == 200
    g = r2.json()
    assert g["ryans_decision"] == "Pursue"
    assert g["outcome"] == "Pending"
    assert g["next_follow_up"] == "2026-03-01"
    assert g["status"] == "Conversation started"


def test_patch_fields_empty_body(client):
    r = client.patch(f"{API}/opportunities/opp_004/fields", json={}, timeout=15)
    assert r.status_code == 400


def test_patch_fields_missing_id(client):
    r = client.patch(f"{API}/opportunities/missing_id/fields",
                     json={"outcome": "Pending"}, timeout=15)
    assert r.status_code == 404


# ---------- iteration 2: Airtable module structural checks ----------
def test_airtable_module_constants():
    import sys
    sys.path.insert(0, "/app/backend")
    from services.airtable_service import (
        AirtableOpportunityService,
        KNOWN_FIELD_MAP,
        EDITABLE_FIELDS,
        READONLY_FIELD_TYPES,
        build_airtable_service_from_env,
    )

    # KNOWN_FIELD_MAP maps Airtable names -> snake_case
    assert KNOWN_FIELD_MAP["Status"] == "status"
    assert KNOWN_FIELD_MAP["Ryan's Decision"] == "ryans_decision"
    assert KNOWN_FIELD_MAP["Next Follow Up"] == "next_follow_up"
    assert KNOWN_FIELD_MAP["Outcome"] == "outcome"

    # EDITABLE_FIELDS is exactly the 4 whitelisted fields
    assert EDITABLE_FIELDS == {"Status", "Ryan's Decision", "Next Follow Up", "Outcome"}

    # Read-only types include formula/rollup/lookup/createdTime/lastModifiedTime
    for t in ("formula", "rollup", "lookup", "createdTime", "lastModifiedTime"):
        assert t in READONLY_FIELD_TYPES

    # Service class advertises "airtable" backend name
    assert AirtableOpportunityService.backend_name == "airtable"


def test_build_airtable_service_from_env_returns_none_when_disabled():
    import sys
    sys.path.insert(0, "/app/backend")
    from services.airtable_service import build_airtable_service_from_env
    # AIRTABLE_ENABLED=false in .env — should return None without any live call.
    assert build_airtable_service_from_env() is None

