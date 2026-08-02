"""
Tests for POST /api/leads/{id}/action approve flow — actually sends email via
Emergent-managed Resend integration.

Recipient is ALWAYS delivered@resend.dev (Resend's noop test address).
Every test restores mutated Airtable fields in a finally block.
"""
import os
import time
import pytest
import requests
from dotenv import load_dotenv
from pathlib import Path
from pyairtable import Api

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # fallback to frontend .env
    import re
    fe = Path("/app/frontend/.env").read_text()
    m = re.search(r"REACT_APP_BACKEND_URL=(.+)", fe)
    BASE_URL = m.group(1).strip() if m else None
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
BASE_URL = BASE_URL.rstrip("/")

AIRTABLE_KEY = os.environ["AIRTABLE_API_KEY"]
AIRTABLE_BASE = os.environ["AIRTABLE_BASE_ID"]
AIRTABLE_TABLE = os.environ.get("AIRTABLE_LEADS_TABLE", "Leads")

TEST_LEAD_ID = "rec1j1S6sVvAu0ofb"
TEST_RECIPIENT = "delivered@resend.dev"

SEND_FIELDS = [
    "Outreach sent", "Message sent date", "Outreach channel",
    "Approval status", "Outreach status", "First message",
    "Contact email", "Status", "Hunt status",
]


@pytest.fixture(scope="module")
def airtable_table():
    api = Api(AIRTABLE_KEY)
    return api.table(AIRTABLE_BASE, AIRTABLE_TABLE)


def _snapshot(table, lead_id, keys):
    rec = table.get(lead_id)
    fields = rec.get("fields", {})
    return {k: fields.get(k) for k in keys}


def _restore(table, lead_id, snapshot):
    """Reset fields to their original values, clearing what was empty."""
    payload = {}
    for k, v in snapshot.items():
        if v is None or v == "" or v is False:
            # clearing
            payload[k] = None
        else:
            payload[k] = v
    try:
        table.update(lead_id, payload, typecast=True)
    except Exception as e:
        print(f"Restore failed: {e}")


def _reload():
    """Force the backend to drop cached opportunity/leads state where possible."""
    try:
        requests.post(f"{BASE_URL}/api/admin/reload", timeout=15)
    except Exception:
        pass
    # Leads service does not have a reset endpoint — its cache TTL is 45s.
    # Best-effort: sleep a bit less than that so subsequent calls see fresh data.
    time.sleep(1)


# ---------- SMOKE ----------

class TestSmoke:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("backend") == "airtable"
        assert data.get("count", 0) > 0

    def test_opportunities_list(self):
        r = requests.get(f"{BASE_URL}/api/opportunities", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) > 0

    def test_nba_queue(self):
        r = requests.get(f"{BASE_URL}/api/leads/next-best-action", timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert body.get("lead") is not None
        assert body["lead"].get("id")

    def test_patch_fields_empty(self):
        r = requests.patch(
            f"{BASE_URL}/api/opportunities/{TEST_LEAD_ID}/fields",
            json={},
            timeout=20,
        )
        assert r.status_code == 200

    def test_patch_fields_unknown_only(self):
        r = requests.patch(
            f"{BASE_URL}/api/opportunities/{TEST_LEAD_ID}/fields",
            json={"foo": "bar"},
            timeout=20,
        )
        assert r.status_code == 200


# ---------- SUCCESS: fallback template ----------

class TestApproveSuccessFallback:
    def test_success_path_fallback(self, airtable_table):
        snap = _snapshot(airtable_table, TEST_LEAD_ID, SEND_FIELDS)
        try:
            # Prep: set contact email, clear first message so fallback kicks in.
            airtable_table.update(
                TEST_LEAD_ID,
                {
                    "Contact email": TEST_RECIPIENT,
                    "First message": None,
                    "Outreach sent": None,
                    "Message sent date": None,
                    "Outreach channel": None,
                    "Approval status": None,
                    "Outreach status": None,
                },
                typecast=True,
            )
            _reload()

            r = requests.post(
                f"{BASE_URL}/api/leads/{TEST_LEAD_ID}/action",
                json={"action": "approve"},
                timeout=60,
            )
            assert r.status_code == 200, f"got {r.status_code} body={r.text}"
            body = r.json()
            assert body["state"] == "sent"
            assert body["channel"] == "Email"
            assert body["recipient"] == TEST_RECIPIENT
            assert body["used_fallback_template"] is True
            assert body.get("provider_id"), f"provider_id missing: {body}"
            persisted = body.get("persisted") or {}
            for k in ("Outreach sent", "Message sent date", "Outreach channel",
                      "Approval status", "Outreach status", "First message"):
                assert persisted.get(k) is True, f"persist flag missing for {k}: {persisted}"

            # Verify on Airtable
            time.sleep(2)
            rec = airtable_table.get(TEST_LEAD_ID)
            f = rec["fields"]
            assert f.get("Outreach sent") is True
            assert f.get("Message sent date")
            assert f.get("Outreach channel") == "Email"
            assert f.get("Approval status") == "Approved"
            assert f.get("Outreach status") == "Sent"
            fm = f.get("First message") or ""
            assert fm.startswith("Hi "), f"fallback body missing: {fm[:120]!r}"
        finally:
            _restore(airtable_table, TEST_LEAD_ID, snap)


# ---------- SUCCESS: caller-provided First message ----------

class TestApproveSuccessCustom:
    def test_success_path_custom_message(self, airtable_table):
        snap = _snapshot(airtable_table, TEST_LEAD_ID, SEND_FIELDS)
        custom = "This is my custom outreach body."
        try:
            airtable_table.update(
                TEST_LEAD_ID,
                {
                    "Contact email": TEST_RECIPIENT,
                    "First message": None,
                    "Outreach sent": None,
                    "Message sent date": None,
                    "Outreach channel": None,
                    "Approval status": None,
                    "Outreach status": None,
                },
                typecast=True,
            )
            _reload()

            r = requests.patch(
                f"{BASE_URL}/api/leads/{TEST_LEAD_ID}/message",
                json={"message": custom},
                timeout=30,
            )
            assert r.status_code == 200, r.text
            time.sleep(1)

            r = requests.post(
                f"{BASE_URL}/api/leads/{TEST_LEAD_ID}/action",
                json={"action": "approve"},
                timeout=60,
            )
            assert r.status_code == 200, f"got {r.status_code} body={r.text}"
            body = r.json()
            assert body["state"] == "sent"
            assert body["used_fallback_template"] is False
            assert body.get("provider_id")

            time.sleep(2)
            rec = airtable_table.get(TEST_LEAD_ID)
            fm = rec["fields"].get("First message")
            assert fm == custom, f"expected custom message, got {fm!r}"
        finally:
            _restore(airtable_table, TEST_LEAD_ID, snap)


# ---------- GUARDRAILS ----------

class TestGuardrails:
    def test_no_contact_email(self, airtable_table):
        snap = _snapshot(airtable_table, TEST_LEAD_ID, SEND_FIELDS)
        try:
            airtable_table.update(
                TEST_LEAD_ID,
                {
                    "Contact email": None,
                    "Email": None,
                    "Phone number": None,
                    "Outreach sent": None,
                    "Approval status": None,
                    "Outreach status": None,
                },
                typecast=True,
            )
            _reload()

            r = requests.post(
                f"{BASE_URL}/api/leads/{TEST_LEAD_ID}/action",
                json={"action": "approve"},
                timeout=60,
            )
            assert r.status_code == 422, f"expected 422 got {r.status_code} {r.text}"
            detail = (r.json().get("detail") or "").lower()
            assert "contact email" in detail or "no contact" in detail, detail

            rec = airtable_table.get(TEST_LEAD_ID)
            assert not rec["fields"].get("Outreach sent")
        finally:
            _restore(airtable_table, TEST_LEAD_ID, snap)

    def test_status_do_not_contact(self, airtable_table):
        snap = _snapshot(airtable_table, TEST_LEAD_ID, SEND_FIELDS)
        try:
            airtable_table.update(
                TEST_LEAD_ID,
                {
                    "Contact email": TEST_RECIPIENT,
                    "Status": "Do Not Contact",
                    "Outreach sent": None,
                    "Approval status": None,
                    "Outreach status": None,
                },
                typecast=True,
            )
            _reload()

            r = requests.post(
                f"{BASE_URL}/api/leads/{TEST_LEAD_ID}/action",
                json={"action": "approve"},
                timeout=60,
            )
            assert r.status_code == 422, f"expected 422 got {r.status_code} {r.text}"
            detail = (r.json().get("detail") or "").lower()
            assert "status" in detail and "do not contact" in detail, detail
        finally:
            _restore(airtable_table, TEST_LEAD_ID, snap)

    def test_hunt_status_rejected(self, airtable_table):
        snap = _snapshot(airtable_table, TEST_LEAD_ID, SEND_FIELDS)
        try:
            airtable_table.update(
                TEST_LEAD_ID,
                {
                    "Contact email": TEST_RECIPIENT,
                    "Hunt status": "Rejected",
                    "Outreach sent": None,
                    "Approval status": None,
                    "Outreach status": None,
                },
                typecast=True,
            )
            _reload()

            r = requests.post(
                f"{BASE_URL}/api/leads/{TEST_LEAD_ID}/action",
                json={"action": "approve"},
                timeout=60,
            )
            # If the guardrail is implemented, we expect 422 referencing Hunt status.
            # If the LEADS_FIELD_MAP omits Hunt status (current code!), the guardrail
            # cannot fire and this returns 200 (send happens). Document the exact
            # observed behavior.
            body = r.text
            assert r.status_code == 422, (
                f"HUNT-STATUS guardrail did NOT block send. "
                f"Got {r.status_code} body={body[:400]}. "
                "Likely cause: LEADS_FIELD_MAP in leads_service.py is missing 'Hunt status' — "
                "so the read-DTO never surfaces hunt_status and can_send() cannot check it."
            )
            detail = (r.json().get("detail") or "").lower()
            assert "hunt status" in detail, detail
        finally:
            _restore(airtable_table, TEST_LEAD_ID, snap)


# ---------- REGRESSIONS ----------

class TestRegressions:
    def test_hold_action(self, airtable_table):
        snap = _snapshot(airtable_table, TEST_LEAD_ID, SEND_FIELDS)
        try:
            r = requests.post(
                f"{BASE_URL}/api/leads/{TEST_LEAD_ID}/action",
                json={"action": "hold"},
                timeout=30,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body.get("state") == "hold"
        finally:
            _restore(airtable_table, TEST_LEAD_ID, snap)

    def test_skip_action(self):
        # Skip is session-only and safe.
        r = requests.post(
            f"{BASE_URL}/api/leads/{TEST_LEAD_ID}/action",
            json={"action": "skip"},
            timeout=30,
        )
        assert r.status_code == 200
        assert r.json().get("state") == "skipped"

    def test_do_not_contact_requires_confirm(self):
        r = requests.post(
            f"{BASE_URL}/api/leads/{TEST_LEAD_ID}/action",
            json={"action": "do_not_contact"},
            timeout=30,
        )
        assert r.status_code == 400
