"""
Backend regression tests after airtable_service was rewired to the Leads table.
Covers /api/health, /api/opportunities* and PATCH /api/opportunities/{id}/fields
plus a regression check on /api/leads/next-best-action.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://branch-verify-build.preview.emergentagent.com").rstrip("/")

SAMPLE_NAMES = {"Uptown Colonial Rehab", "Warehouse District Loft"}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---- health / cache-status ----
class TestHealth:
    def test_health_backend_airtable(self, client):
        r = client.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["backend"] == "airtable"
        assert data["count"] == 113

    def test_cache_status(self, client):
        r = client.get(f"{BASE_URL}/api/cache-status")
        assert r.status_code == 200
        d = r.json()
        assert d["backend"] == "airtable"
        assert d["count"] == 113
        assert d["is_refreshing"] is False


# ---- opportunities list & shape ----
class TestOpportunities:
    def test_list_113_real_names(self, client):
        r = client.get(f"{BASE_URL}/api/opportunities")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 113
        names = {o.get("name") for o in data}
        assert not (names & SAMPLE_NAMES), f"Sample names leaked: {names & SAMPLE_NAMES}"
        # Expected leads present
        assert any(n and "Maggiore" in n for n in names)
        assert any(n and "Tulane Chabad" in n for n in names)
        # Shape
        required = {"name", "id", "status", "daily_mission", "priority_band",
                    "priority_score", "source", "activity_timeline",
                    "missing_information", "risk_flags"}
        first = data[0]
        assert required.issubset(first.keys()), f"missing: {required - set(first.keys())}"
        assert isinstance(first["activity_timeline"], list)
        assert isinstance(first["missing_information"], list)
        assert isinstance(first["risk_flags"], list)

    def test_list_min_score_filter(self, client):
        r = client.get(f"{BASE_URL}/api/opportunities?min_score=1")
        assert r.status_code == 200
        data = r.json()
        # Spec: roughly 79
        assert 70 <= len(data) <= 90, f"expected ~79 leads with priority_score>0, got {len(data)}"

    def test_summary(self, client):
        r = client.get(f"{BASE_URL}/api/opportunities/summary")
        assert r.status_code == 200
        d = r.json()
        assert d["total_count"] == 113
        assert d["active_count"] == 113
        assert d["new_opportunities"] == 40
        assert d["needs_research"] >= 70
        assert d["ready_to_contact"] == 1

    def test_pipeline(self, client):
        r = client.get(f"{BASE_URL}/api/opportunities/pipeline")
        assert r.status_code == 200
        stages = r.json()
        assert isinstance(stages, list)
        assert len(stages) == 9
        by_status = {s["status"]: s["count"] for s in stages}
        assert sum(by_status.values()) == 113
        assert by_status.get("Needs research", 0) >= 70
        assert by_status.get("New") == 40

    def test_missions(self, client):
        r = client.get(f"{BASE_URL}/api/opportunities/missions")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, dict)
        counts = {k: len(v) for k, v in d.items()}
        assert counts.get("Research First", 0) >= 60
        # These buckets should exist as keys (may or may not be non-empty)
        for k in ("Wait", "Send Email", "Prepare Estimate", "Research First"):
            assert k in d
        # At least these three have entries per spec
        assert counts.get("Wait", 0) > 0
        assert counts.get("Send Email", 0) > 0
        assert counts.get("Prepare Estimate", 0) > 0

    def test_recent_5(self, client):
        r = client.get(f"{BASE_URL}/api/opportunities/recent?limit=5")
        assert r.status_code == 200
        d = r.json()
        assert len(d) == 5
        for o in d:
            assert o.get("id", "").startswith("rec")

    def test_get_single(self, client):
        listing = client.get(f"{BASE_URL}/api/opportunities").json()
        oid = listing[0]["id"]
        r = client.get(f"{BASE_URL}/api/opportunities/{oid}")
        assert r.status_code == 200
        d = r.json()
        assert d["id"] == oid
        assert isinstance(d["missing_information"], list)
        assert isinstance(d["risk_flags"], list)
        assert isinstance(d["activity_timeline"], list)


# ---- PATCH tests (retest of iteration_4 failures) ----
TARGET_ID = "rec1j1S6sVvAu0ofb"  # AT Tulane Chabad — restore state in each test


class TestPatchFields:
    def test_empty_body_returns_current_dto(self, client):
        """Spec: PATCH with {} returns 200 + current DTO (was 400)."""
        r = client.patch(f"{BASE_URL}/api/opportunities/{TARGET_ID}/fields", json={})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("id") == TARGET_ID
        assert "status" in d and "daily_mission" in d

    def test_unknown_only_body_silent_ignore(self, client):
        """Spec: PATCH with unknown-only fields returns 200 + current DTO (was 400)."""
        r = client.patch(f"{BASE_URL}/api/opportunities/{TARGET_ID}/fields",
                         json={"foo": "bar"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("id") == TARGET_ID

    def test_next_follow_up_clear_via_empty_string(self, client):
        """Spec: PATCH {\"next_follow_up\":\"\"} clears Airtable field, returns 200 (was 500)."""
        # first ensure it has some value we can clear (or leave existing)
        set_r = client.patch(f"{BASE_URL}/api/opportunities/{TARGET_ID}/fields",
                             json={"next_follow_up": "2026-09-01"})
        assert set_r.status_code == 200, set_r.text
        time.sleep(1)
        # Now clear
        r = client.patch(f"{BASE_URL}/api/opportunities/{TARGET_ID}/fields",
                        json={"next_follow_up": ""})
        assert r.status_code == 200, f"expected 200 on clear, got {r.status_code}: {r.text}"
        d = r.json()
        assert d.get("next_follow_up") in (None, ""), f"next_follow_up not cleared: {d.get('next_follow_up')}"

    def test_status_ready_persists_via_typecast(self, client):
        """Spec: PATCH status=Ready persists (typecast=True) or gracefully 4xx (not 500)."""
        # Grab original status to restore
        current = client.get(f"{BASE_URL}/api/opportunities/{TARGET_ID}").json()
        original_status_raw = current.get("status_raw")
        try:
            r = client.patch(f"{BASE_URL}/api/opportunities/{TARGET_ID}/fields",
                             json={"status": "Ready"})
            assert r.status_code != 500, f"500 on status=Ready: {r.text[:300]}"
            assert r.status_code == 200, f"expected 200 with typecast, got {r.status_code}: {r.text[:300]}"
            d = r.json()
            # value written to Status field (dashboard remap may show as 'Ready')
            assert d.get("status_raw") == "Ready" or d.get("status") == "Ready", \
                f"status not persisted: status={d.get('status')} status_raw={d.get('status_raw')}"
        finally:
            time.sleep(1)
            restore_val = original_status_raw if original_status_raw else "New"
            client.patch(f"{BASE_URL}/api/opportunities/{TARGET_ID}/fields",
                         json={"status": restore_val})

    def test_ryans_decision_investigating(self, client):
        """Spec: PATCH ryans_decision writes to Hunt status via WRITE_ALIAS, returns 200."""
        current = client.get(f"{BASE_URL}/api/opportunities/{TARGET_ID}").json()
        original = current.get("hunt_status")
        try:
            r = client.patch(f"{BASE_URL}/api/opportunities/{TARGET_ID}/fields",
                             json={"ryans_decision": "Investigating"})
            assert r.status_code != 500, f"500: {r.text[:300]}"
            assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:300]}"
            d = r.json()
            assert d.get("hunt_status") == "Investigating" or d.get("ryans_decision") == "Investigating"
        finally:
            time.sleep(1)
            client.patch(f"{BASE_URL}/api/opportunities/{TARGET_ID}/fields",
                         json={"ryans_decision": original if original else ""})

    def test_outcome_wrong_fit(self, client):
        """Spec: PATCH outcome writes to Rejection reason, returns 200."""
        current = client.get(f"{BASE_URL}/api/opportunities/{TARGET_ID}").json()
        original = current.get("outcome")
        try:
            r = client.patch(f"{BASE_URL}/api/opportunities/{TARGET_ID}/fields",
                             json={"outcome": "Wrong Fit"})
            assert r.status_code != 500, f"500: {r.text[:300]}"
            assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:300]}"
            d = r.json()
            assert d.get("outcome") == "Wrong Fit"
        finally:
            time.sleep(1)
            client.patch(f"{BASE_URL}/api/opportunities/{TARGET_ID}/fields",
                         json={"outcome": original if original else ""})


# ---- leads regression ----
class TestLeadsRegression:
    def test_next_best_action_populated(self, client):
        r = client.get(f"{BASE_URL}/api/leads/next-best-action")
        assert r.status_code == 200
        d = r.json()
        assert "lead" in d and "queue" in d
        lead = d["lead"]
        assert lead.get("name")
        assert lead.get("next_action")
        assert lead.get("id", "").startswith("rec")
        q = d["queue"]
        assert q["total"] == 113
        assert isinstance(q["eligible"], int)

    def test_skip_action(self, client):
        first = client.get(f"{BASE_URL}/api/leads/next-best-action").json()["lead"]
        lid = first["id"]
        r = client.post(f"{BASE_URL}/api/leads/{lid}/action", json={"action": "skip"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("state") == "skipped"
