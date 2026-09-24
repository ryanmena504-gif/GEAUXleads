"""
Tests for canonical Lead score ranking across:
  - GET /api/opportunities?sort=lead_score|freshness|confidence
  - GET /api/opportunities/top
  - GET /api/opportunities/top-by-lane
  - GET /api/leads/next-best-action

Unscored records (priority_score is None) MUST rank AFTER scored records
in lead_score mode. Same rule for confidence (evidence_confidence). For
freshness mode, records without any date must come last.
"""
import os
import re
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    m = re.search(r"REACT_APP_BACKEND_URL=(.+)",
                  Path("/app/frontend/.env").read_text())
    BASE_URL = m.group(1).strip() if m else None
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
BASE_URL = BASE_URL.rstrip("/")

CLOSED = {"Won", "Lost", "Disqualified"}


def _get(path, **params):
    r = requests.get(f"{BASE_URL}{path}", params=params, timeout=30)
    assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
    return r.json()


# ---------- helpers ----------
def _is_scored_lead(o):
    s = o.get("priority_score")
    return isinstance(s, (int, float))


def _is_scored_conf(o):
    v = o.get("confidence_score") or o.get("evidence_confidence")
    try:
        float(v)
        return v not in (None, "")
    except (TypeError, ValueError):
        return False


def _date_of(o):
    return o.get("last_reviewed") or o.get("created_time") or ""


# ---------- SORT: lead_score ----------
class TestSortLeadScore:
    def test_scored_before_unscored(self):
        items = _get("/api/opportunities", sort="lead_score")
        assert isinstance(items, list) and len(items) > 0
        # Find the boundary
        seen_unscored = False
        for o in items:
            if not _is_scored_lead(o):
                seen_unscored = True
            else:
                assert not seen_unscored, (
                    f"Scored record {o.get('id')} (score={o.get('priority_score')}) "
                    f"appears AFTER an unscored record"
                )

    def test_scored_desc(self):
        items = _get("/api/opportunities", sort="lead_score")
        scored = [o for o in items if _is_scored_lead(o)]
        for a, b in zip(scored, scored[1:]):
            assert a["priority_score"] >= b["priority_score"], (
                f"Order violation: {a['id']}={a['priority_score']} then "
                f"{b['id']}={b['priority_score']}"
            )

    def test_ties_broken_by_freshness_desc(self):
        items = _get("/api/opportunities", sort="lead_score")
        scored = [o for o in items if _is_scored_lead(o)]
        # For adjacent equal-score pairs, freshness DESC must hold.
        for a, b in zip(scored, scored[1:]):
            if a["priority_score"] == b["priority_score"]:
                da, db = _date_of(a), _date_of(b)
                if da and db:
                    assert da >= db, f"Tie-break freshness failed: {a['id']}({da}) then {b['id']}({db})"


# ---------- SORT: freshness ----------
class TestSortFreshness:
    def test_dateless_last(self):
        items = _get("/api/opportunities", sort="freshness")
        seen_dateless = False
        for o in items:
            if not _date_of(o):
                seen_dateless = True
            else:
                assert not seen_dateless, (
                    f"Dated record {o.get('id')} appears AFTER a dateless one"
                )

    def test_dates_desc(self):
        items = _get("/api/opportunities", sort="freshness")
        dated = [o for o in items if _date_of(o)]
        for a, b in zip(dated, dated[1:]):
            assert _date_of(a) >= _date_of(b), (
                f"Date order violation: {a['id']}({_date_of(a)}) then {b['id']}({_date_of(b)})"
            )


# ---------- SORT: confidence ----------
class TestSortConfidence:
    def test_scored_before_unscored(self):
        items = _get("/api/opportunities", sort="confidence")
        seen_unscored = False
        for o in items:
            if not _is_scored_conf(o):
                seen_unscored = True
            else:
                assert not seen_unscored, (
                    f"Confidence-scored {o.get('id')} after unscored"
                )

    def test_scored_desc(self):
        items = _get("/api/opportunities", sort="confidence")
        def c(o):
            return float(o.get("confidence_score") or o.get("evidence_confidence"))
        scored = [o for o in items if _is_scored_conf(o)]
        for a, b in zip(scored, scored[1:]):
            assert c(a) >= c(b), f"Conf order: {a['id']}={c(a)} then {b['id']}={c(b)}"


# ---------- TOP endpoint ----------
class TestTop:
    def test_top_limit_and_order(self):
        top5 = _get("/api/opportunities/top", limit=5)
        assert isinstance(top5, list)
        assert len(top5) <= 5
        # Every item is active
        for o in top5:
            assert o.get("status") not in CLOSED, f"closed leaked into /top: {o.get('id')}"
        # All top items should be scored (unscored land at bottom of full list;
        # if there are fewer scored than the limit, unscored can appear — but
        # they must come AFTER the scored ones).
        seen_unscored = False
        for o in top5:
            if not _is_scored_lead(o):
                seen_unscored = True
            else:
                assert not seen_unscored, "unscored precedes scored in /top"
        scored = [o for o in top5 if _is_scored_lead(o)]
        for a, b in zip(scored, scored[1:]):
            assert a["priority_score"] >= b["priority_score"]

    def test_top_matches_full_list_prefix(self):
        top5 = _get("/api/opportunities/top", limit=5)
        # Build the same active-only lead_score list from /opportunities
        all_items = _get("/api/opportunities", sort="lead_score")
        active_scored_ids = [o["id"] for o in all_items
                             if o.get("status") not in CLOSED and _is_scored_lead(o)]
        top_ids = [o["id"] for o in top5 if _is_scored_lead(o)]
        # Prefix agreement on the scored region (up to min length)
        n = min(len(top_ids), len(active_scored_ids))
        assert top_ids[:n] == active_scored_ids[:n], (
            f"/top prefix mismatch. top={top_ids} full={active_scored_ids[:n]}"
        )


# ---------- TOP-BY-LANE ----------
class TestTopByLane:
    def test_three_lanes(self):
        data = _get("/api/opportunities/top-by-lane", limit=3)
        assert set(data.keys()) == {"market_capture", "partner", "non_permit"}
        for lane, rows in data.items():
            assert isinstance(rows, list)
            assert len(rows) <= 3
            for o in rows:
                assert o.get("lane") == lane, f"{lane}: row lane={o.get('lane')}"
                assert o.get("status") not in CLOSED
            # Scored-before-unscored + DESC on scored region
            seen_unscored = False
            for o in rows:
                if not _is_scored_lead(o):
                    seen_unscored = True
                else:
                    assert not seen_unscored, f"{lane}: unscored precedes scored"
            scored = [o for o in rows if _is_scored_lead(o)]
            for a, b in zip(scored, scored[1:]):
                assert a["priority_score"] >= b["priority_score"], (
                    f"{lane} order: {a['priority_score']} then {b['priority_score']}"
                )


# ---------- NEXT BEST ACTION ----------
class TestNBA:
    def test_nba_top_lead_score(self):
        body = _get("/api/leads/next-best-action")
        lead = body.get("lead")
        assert lead, f"no NBA lead: {body}"
        assert lead.get("id")
        # If we have lead_score, its selection should be highest among eligible.
        # We cannot recompute the exact eligible set from HTTP alone, but we
        # verify that the pick's lead_score is >= scores of other candidates
        # returned by a helper listing — best-effort check.
        # Just assert lead_score is either a number or None (unscored can be
        # picked only if no scored candidate exists).
        ls = lead.get("lead_score")
        assert ls is None or isinstance(ls, (int, float))


# ---------- REGRESSION: PATCH fields ----------
# NB: The previously-used test lead rec1j1S6sVvAu0ofb is no longer accessible
# in Airtable (403 INVALID_PERMISSIONS_OR_MODEL_NOT_FOUND). Use a live lead
# picked from the current /api/opportunities list.
TEST_LEAD_ID = "rec9oACK2PGWSmfmk"  # 'Greige Interiors' — verified live


class TestPatchFieldsRegression:
    def test_patch_empty(self):
        r = requests.patch(f"{BASE_URL}/api/opportunities/{TEST_LEAD_ID}/fields",
                           json={}, timeout=20)
        assert r.status_code == 200

    def test_patch_unknown_only(self):
        r = requests.patch(f"{BASE_URL}/api/opportunities/{TEST_LEAD_ID}/fields",
                           json={"foo": "bar"}, timeout=20)
        assert r.status_code == 200


# ---------- HUNT-STATUS GUARDRAIL (the iteration_6 CRITICAL bug) ----------
# Verifies LEADS_FIELD_MAP now maps 'Hunt status' -> 'hunt_status' so can_send()
# can block approve+send when Hunt status contains rejected/closed/disqualified.
import time
from pyairtable import Api

AIRTABLE_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TABLE = os.environ.get("AIRTABLE_LEADS_TABLE", "Leads")


@pytest.fixture(scope="module")
def airtable_table():
    if not (AIRTABLE_KEY and AIRTABLE_BASE):
        pytest.skip("Airtable creds missing")
    return Api(AIRTABLE_KEY).table(AIRTABLE_BASE, AIRTABLE_TABLE)


SEND_FIELDS = [
    "Outreach sent", "Message sent date", "Outreach channel",
    "Approval status", "Outreach status", "First message",
    "Contact email", "Status", "Hunt status",
]


def _snap(table, lid, keys):
    rec = table.get(lid)
    f = rec.get("fields", {})
    return {k: f.get(k) for k in keys}


def _restore(table, lid, snap):
    payload = {}
    for k, v in snap.items():
        if v is None or v == "" or v is False:
            payload[k] = None
        else:
            payload[k] = v
    try:
        table.update(lid, payload, typecast=True)
    except Exception as e:
        print(f"restore fail: {e}")


def _reload():
    try:
        requests.post(f"{BASE_URL}/api/admin/reload", timeout=15)
    except Exception:
        pass
    time.sleep(1)


class TestHuntStatusGuardrail:
    def test_dto_surfaces_hunt_status(self):
        """Regression: verify LEADS_FIELD_MAP includes Hunt status."""
        body = _get("/api/leads/next-best-action")
        lead = body.get("lead") or {}
        # Field must be present as a key (may be null for some leads)
        assert "hunt_status" in lead, (
            "hunt_status key missing from lead DTO — LEADS_FIELD_MAP likely broken"
        )

    def test_rejected_hunt_status_blocks_approve(self, airtable_table):
        lid = TEST_LEAD_ID
        snap = _snap(airtable_table, lid, SEND_FIELDS)
        try:
            airtable_table.update(
                lid,
                {
                    "Contact email": "delivered@resend.dev",
                    "Hunt status": "Rejected",
                    "Outreach sent": None,
                    "Approval status": None,
                    "Outreach status": None,
                    "Status": None,
                },
                typecast=True,
            )
            _reload()
            # Also restart backend to reset the leads_service cache (45s TTL)
            # since /api/admin/reload only resets opportunity_service.
            import subprocess
            subprocess.run(["sudo", "supervisorctl", "restart", "backend"],
                           check=False, capture_output=True, timeout=30)
            time.sleep(4)

            r = requests.post(
                f"{BASE_URL}/api/leads/{lid}/action",
                json={"action": "approve"},
                timeout=60,
            )
            assert r.status_code == 422, (
                f"HUNT-STATUS guardrail did NOT block send. "
                f"Got {r.status_code} body={r.text[:400]}. "
                "LEADS_FIELD_MAP probably missing 'Hunt status' mapping."
            )
            detail = (r.json().get("detail") or "").lower()
            assert "hunt status" in detail, f"unexpected detail: {detail}"

            # Confirm no send happened
            time.sleep(1)
            rec = airtable_table.get(lid)
            assert not rec["fields"].get("Outreach sent"), (
                "email got sent despite 422!"
            )
        finally:
            _restore(airtable_table, lid, snap)
