"""
Backend regression tests after airtable_service was rewired to the Leads table.
Covers /api/health, /api/opportunities* and PATCH /api/opportunities/{id}/fields
plus a regression check on /api/leads/next-best-action.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hound-priorities.preview.emergentagent.com").rstrip("/")

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


# ---- PATCH tests ----
class TestPatchFields:
    # Use a boring lead (skeleton row) to minimise data pollution
    @pytest.fixture(scope="class")
    def target_id(self, client):
        # pick a lead that has an empty next_follow_up so we can restore safely
        data = client.get(f"{BASE_URL}/api/opportunities").json()
        for o in data:
            if not o.get("next_follow_up"):
                return o["id"]
        return data[0]["id"]

    def test_next_follow_up_persists_and_restore(self, client, target_id):
        # Set
        r = client.patch(f"{BASE_URL}/api/opportunities/{target_id}/fields",
                         json={"next_follow_up": "2026-09-01"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("next_follow_up", "").startswith("2026-09-01")
        time.sleep(1)
        # Restore by writing an empty string (null gets stripped by exclude_none)
        r2 = client.patch(f"{BASE_URL}/api/opportunities/{target_id}/fields",
                          json={"next_follow_up": ""})
        # Accept either 200 (cleared) or 400 (backend strips empty) — flag if 500
        assert r2.status_code in (200, 400), f"got {r2.status_code}: {r2.text}"

    def test_status_ready_persists(self, client, target_id):
        """Spec: PATCH status=Ready should persist. If Airtable single-select
        lacks 'Ready' option, backend should return graceful 4xx, NOT 500."""
        r = client.patch(f"{BASE_URL}/api/opportunities/{target_id}/fields",
                         json={"status": "Ready"})
        assert r.status_code != 500, f"500 on status=Ready: {r.text[:200]}"
        if r.status_code == 200:
            # Restore
            time.sleep(1)
            client.patch(f"{BASE_URL}/api/opportunities/{target_id}/fields",
                         json={"status": ""})

    def test_ryans_decision_graceful(self, client, target_id):
        """Hunt status may reject unknown select option — must be 4xx not 500."""
        r = client.patch(f"{BASE_URL}/api/opportunities/{target_id}/fields",
                         json={"ryans_decision": "Investigating"})
        assert r.status_code != 500, f"500 on ryans_decision: {r.text[:200]}"
        assert r.status_code < 500

    def test_unknown_field_ignored(self, client, target_id):
        """Spec: unknown fields silently ignored, returns current DTO."""
        r = client.patch(f"{BASE_URL}/api/opportunities/{target_id}/fields",
                         json={"unknown_field": "x"})
        assert r.status_code != 500
        # Spec requires 200 with current DTO; current impl returns 400.
        # Flag as failure for main agent.
        assert r.status_code == 200, f"expected 200 with current DTO, got {r.status_code}: {r.text}"


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
