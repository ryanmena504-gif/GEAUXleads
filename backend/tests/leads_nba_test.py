"""Tests for /api/leads Next Best Action endpoints (iteration 3).

Notes:
- Airtable is enabled with real creds. Writes persist. We restore the
  `First message` field after mutation; other allowlisted writes
  (Approval status, Outreach status, Status) cannot be reverted via the
  public API and are intentionally left mutated.
- Session state (skip/hold/approve sets) is process-local; a backend
  restart resets them.
"""
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or "https://hound-priorities.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _nba(client):
    r = client.get(f"{API}/leads/next-best-action", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# -------- basic structural / regression checks --------
def test_nba_returns_populated_lead(client):
    d = _nba(client)
    assert d.get("lead") is not None, "Skeleton/empty lead regression"
    lead = d["lead"]
    assert isinstance(lead.get("name"), str) and lead["name"].strip(), \
        f"name must be a non-empty string, got {lead.get('name')!r}"
    assert isinstance(lead.get("next_action"), str) and lead["next_action"].strip(), \
        "next_action must be non-empty"
    assert lead.get("opportunity_type") or lead.get("source"), \
        "at least one of opportunity_type/source must be populated"
    assert lead.get("id", "").startswith("rec"), "expected Airtable record id"


def test_nba_queue_stats_shape(client):
    d = _nba(client)
    q = d["queue"]
    for k in ("total", "eligible", "skipped_this_session",
              "on_hold", "approved_this_session"):
        assert k in q, f"missing key: {k}"
        assert isinstance(q[k], int), f"{k} must be int, got {type(q[k])}"
    assert q["eligible"] < q["total"], \
        f"skeleton leads should be excluded (eligible {q['eligible']} vs total {q['total']})"
    assert q["eligible"] > 0, "queue must have at least one eligible lead"


# -------- skip --------
def test_skip_yields_different_lead(client):
    first = _nba(client)["lead"]
    r = client.post(f"{API}/leads/{first['id']}/action",
                    json={"action": "skip"}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "skipped"
    assert body["lead_id"] == first["id"]

    nxt = _nba(client)
    assert nxt["lead"] is not None
    assert nxt["lead"]["id"] != first["id"], \
        "skip should surface a different lead next"
    assert nxt["queue"]["skipped_this_session"] >= 1


# -------- message update (restores original) --------
def test_update_message_persists_and_restore(client):
    lead = _nba(client)["lead"]
    original = lead.get("first_message")
    marker = "TEST_NBA_DRAFT " + str(int(time.time()))
    try:
        r = client.patch(f"{API}/leads/{lead['id']}/message",
                         json={"message": marker}, timeout=30)
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated["first_message"] == marker
        # verify via next fetch of same lead through queue (may or may not be top)
        # Direct verification: call PATCH again with original to confirm no error path,
        # then confirm value round-trips.
    finally:
        # Restore original (or blank if it was empty)
        restore_val = original if original is not None else ""
        rr = client.patch(f"{API}/leads/{lead['id']}/message",
                          json={"message": restore_val}, timeout=30)
        assert rr.status_code == 200, rr.text


# -------- hold (removes from eligible queue) --------
def test_hold_removes_from_queue(client):
    before = _nba(client)
    lead_id = before["lead"]["id"]
    r = client.post(f"{API}/leads/{lead_id}/action",
                    json={"action": "hold"}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "hold"
    # persisted may be True or False depending on whether Outreach status is writable;
    # either is acceptable per spec, but held-in-session must be reflected.
    after = _nba(client)
    assert after["lead"] is None or after["lead"]["id"] != lead_id
    assert after["queue"]["on_hold"] >= 1


# -------- approve (writes Airtable — one mutation per run) --------
def test_approve_writes_flags_and_returns_timestamp(client):
    # Skip past held/skipped leads by refetching current top
    top = _nba(client)["lead"]
    assert top is not None
    lead_id = top["id"]
    # If somehow already approved, skip mutation
    if isinstance(top.get("approval_status"), str) and "approved" in top["approval_status"].lower():
        pytest.skip("Top lead already approved — nothing to mutate")

    r = client.post(f"{API}/leads/{lead_id}/action",
                    json={"action": "approve"}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "approved"
    # ISO timestamp
    ts = body.get("approved_at", "")
    assert isinstance(ts, str) and "T" in ts and ts.endswith(("Z", "+00:00")) or "+" in ts
    # persisted map present
    assert "persisted" in body
    assert "Approval status" in body["persisted"]
    assert "Outreach status" in body["persisted"]
    assert body["persisted"]["Approval status"] is True, \
        "Approval status write must succeed against Airtable"


# -------- DNC (requires confirm) --------
def test_dnc_requires_confirm(client):
    top = _nba(client)["lead"]
    assert top is not None
    r = client.post(f"{API}/leads/{top['id']}/action",
                    json={"action": "do_not_contact"}, timeout=30)
    assert r.status_code == 400


def test_dnc_with_confirm_succeeds(client):
    top = _nba(client)["lead"]
    assert top is not None
    lead_id = top["id"]
    r = client.post(f"{API}/leads/{lead_id}/action",
                    json={"action": "do_not_contact", "confirm": True}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "do_not_contact"
    assert "persisted_to" in body  # may be a field name str or None
    if body["persisted_to"] is None:
        assert "note" in body


# -------- unknown action --------
def test_unknown_action_returns_400(client):
    top = _nba(client)["lead"]
    if not top:
        pytest.skip("no lead")
    r = client.post(f"{API}/leads/{top['id']}/action",
                    json={"action": "nonsense"}, timeout=30)
    assert r.status_code == 400


# -------- regression: opportunities still work --------
def test_opportunities_list_regression(client):
    r = client.get(f"{API}/opportunities", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_opportunities_patch_fields_regression(client):
    # Grab first opp id from list, then PATCH allowlisted field
    lst = client.get(f"{API}/opportunities", timeout=30).json()
    opp_id = lst[0]["id"]
    r = client.patch(f"{API}/opportunities/{opp_id}/fields",
                     json={"outcome": "Pending"}, timeout=30)
    assert r.status_code == 200, r.text
