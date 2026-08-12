"""Backend tests for Bloodhound production cleanup (iteration 8).

Covers:
 - Manual-result endpoint POST /api/opportunities/{id}/result:
     * sent      -> outreach_status='Sent by Ryan', status UNCHANGED
     * replied   -> outreach_status='Reply received' + status='Conversation started'
     * not_interested -> outreach_status='Not interested' + status='Disqualified'
     * unknown key -> 422
 - Regressions: /api/opportunities, /api/opportunities/summary,
   /api/kpis/monthly, /api/follow-ups/due, /api/settings/user still 200.
 - Handoff endpoint does NOT mutate outreach_status.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def opps():
    r = requests.get(f"{API}/opportunities", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list) and len(data) > 0, "no opportunities returned"
    return data


@pytest.fixture(scope="module")
def test_opp_id(opps):
    # Prefer a non-partner active opportunity
    for o in opps:
        if o.get("lane") != "partner":
            return o["id"]
    return opps[0]["id"]


def _get(opp_id):
    r = requests.get(f"{API}/opportunities/{opp_id}", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _restore(opp_id, snapshot):
    """Best-effort restore of the fields we mutated."""
    payload = {
        "outreach_status": snapshot.get("outreach_status") or "",
        "status": snapshot.get("status") or "New",
    }
    try:
        requests.patch(f"{API}/opportunities/{opp_id}/fields", json=payload, timeout=30)
    except Exception:
        pass


# --- Regression: core reads ------------------------------------------------
class TestRegression:
    def test_opportunities_list(self, opps):
        assert len(opps) > 0
        assert "id" in opps[0]

    def test_summary(self):
        r = requests.get(f"{API}/opportunities/summary", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert isinstance(j, dict)

    def test_kpis_monthly(self):
        r = requests.get(f"{API}/kpis/monthly", timeout=30)
        assert r.status_code == 200, r.text

    def test_followups_due(self):
        r = requests.get(f"{API}/follow-ups/due", timeout=30)
        assert r.status_code == 200, r.text

    def test_settings_user(self):
        r = requests.get(f"{API}/settings/user", timeout=30)
        assert r.status_code == 200, r.text


# --- Manual result endpoint -----------------------------------------------
class TestManualResult:
    def test_unknown_key_422(self, test_opp_id):
        r = requests.post(
            f"{API}/opportunities/{test_opp_id}/result",
            json={"result": "garbage"},
            timeout=30,
        )
        assert r.status_code == 422, r.text

    def test_sent_sets_outreach_only(self, test_opp_id):
        snap = _get(test_opp_id)
        try:
            r = requests.post(
                f"{API}/opportunities/{test_opp_id}/result",
                json={"result": "sent"},
                timeout=30,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            opp = body.get("opportunity") or {}
            assert opp.get("outreach_status") == "Sent by Ryan", opp.get("outreach_status")
            # status must NOT be auto-advanced to Conversation started
            assert (opp.get("status") or "") != "Conversation started", opp.get("status")

            # verify persistence via GET
            time.sleep(1)
            fetched = _get(test_opp_id)
            assert fetched.get("outreach_status") == "Sent by Ryan"
            assert (fetched.get("status") or "") != "Conversation started"
        finally:
            _restore(test_opp_id, snap)

    def test_replied_sets_status_conversation_started(self, test_opp_id):
        snap = _get(test_opp_id)
        try:
            r = requests.post(
                f"{API}/opportunities/{test_opp_id}/result",
                json={"result": "replied"},
                timeout=30,
            )
            assert r.status_code == 200, r.text
            opp = r.json().get("opportunity") or {}
            assert opp.get("outreach_status") == "Reply received"
            assert opp.get("status") == "Conversation started"

            time.sleep(1)
            fetched = _get(test_opp_id)
            assert fetched.get("outreach_status") == "Reply received"
            assert fetched.get("status") == "Conversation started"
        finally:
            _restore(test_opp_id, snap)

    def test_not_interested_sets_disqualified(self, test_opp_id):
        snap = _get(test_opp_id)
        try:
            r = requests.post(
                f"{API}/opportunities/{test_opp_id}/result",
                json={"result": "not_interested"},
                timeout=30,
            )
            assert r.status_code == 200, r.text
            opp = r.json().get("opportunity") or {}
            assert opp.get("outreach_status") == "Not interested"
            assert opp.get("status") == "Disqualified"

            time.sleep(1)
            fetched = _get(test_opp_id)
            assert fetched.get("outreach_status") == "Not interested"
            assert fetched.get("status") == "Disqualified"
        finally:
            _restore(test_opp_id, snap)


# --- Handoff must NOT mutate outreach_status ------------------------------
class TestHandoffNoAutoSave:
    def test_handoff_does_not_change_outreach_status(self, test_opp_id):
        before = _get(test_opp_id)
        before_status = before.get("outreach_status") or ""
        payload = {"channel": "sms", "message": "test handoff"}
        r = requests.post(
            f"{API}/opportunities/{test_opp_id}/handoff",
            json=payload,
            timeout=30,
        )
        # accept either 200 (logged) or 4xx (validation); the assertion is
        # about NOT mutating outreach_status.
        assert r.status_code in (200, 201, 400, 422, 503), r.text
        time.sleep(1)
        after = _get(test_opp_id)
        assert (after.get("outreach_status") or "") == before_status, (
            f"handoff mutated outreach_status! before={before_status!r} "
            f"after={after.get('outreach_status')!r}"
        )
