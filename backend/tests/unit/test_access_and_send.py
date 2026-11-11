"""Password lock, morning-job secret, deep health, and the send refusal.

These tests use the app in-process. They do not call Airtable, Perplexity,
OpenAI, or Gmail.
"""
from __future__ import annotations

import inspect
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from scripts.morning_enrichment import should_run
from services.outreach_policy import do_not_contact_message


CHICAGO = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AIRTABLE_ENABLED", "false")
    monkeypatch.setenv("AIRTABLE_WEBHOOK_ENABLED", "false")
    from services.opportunity_service import reset_opportunity_service
    reset_opportunity_service()
    from server import app
    with TestClient(app) as test_client:
        yield test_client


def test_health_stays_open_when_the_password_is_missing(client, monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    assert client.get("/api/health").status_code == 200
    deep = client.get("/api/health/deep")
    assert deep.status_code in (200, 503)
    assert "leads" in deep.json()
    locked = client.get("/api/config")
    assert locked.status_code == 503
    body = locked.json()
    assert body["error"] == "password_not_configured"
    assert "APP_PASSWORD" in body["detail"]


def test_wrong_password_is_rejected_and_the_right_one_opens_the_api(client, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "correct-horse")
    rejected = client.get("/api/config", headers={"X-App-Password": "nope"})
    assert rejected.status_code == 401
    opened = client.get("/api/config", headers={"X-App-Password": "correct-horse"})
    assert opened.status_code == 200


def test_enrichment_requires_the_cron_secret_and_does_not_call_research(client, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "pw")
    monkeypatch.setenv("WEBHOOK_CRON_SECRET", "cron-secret")
    called = {}

    async def fake_run(svc, dry_run=False, seen=None):
        called["yes"] = True
        return {"ok": True, "processed": 0, "dry_run": dry_run}

    monkeypatch.setattr("services.enrichment_batch.run_for_service", fake_run)
    headers = {"X-App-Password": "pw"}
    missing = client.post("/api/enrichment/run", headers=headers)
    assert missing.status_code == 401
    assert "yes" not in called

    headers["X-Cron-Secret"] = "cron-secret"
    ran = client.post("/api/enrichment/run", headers=headers)
    assert ran.status_code == 200
    assert called.get("yes") is True


def test_missing_cron_secret_fails_closed(client, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "pw")
    monkeypatch.delenv("WEBHOOK_CRON_SECRET", raising=False)
    response = client.post(
        "/api/enrichment/run",
        headers={"X-App-Password": "pw", "X-Cron-Secret": "anything"},
    )
    assert response.status_code == 503
    assert "WEBHOOK_CRON_SECRET" in response.json()["detail"]


def test_deep_health_reports_a_leads_crash(client, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "pw")

    def boom():
        raise NameError("name '_singleton' is not defined")

    monkeypatch.setattr("server.get_leads_service", boom)
    response = client.get("/api/health/deep")
    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert any("NameError" in item for item in body["errors"])
    assert "phone" not in response.text


def test_website_process_does_not_start_a_research_timer():
    from server import lifespan
    assert "enrichment_scheduler" not in inspect.getsource(lifespan)


def test_morning_script_runs_at_7am_chicago_in_winter_and_summer():
    assert should_run(datetime(2026, 1, 15, 7, 30, tzinfo=CHICAGO))
    assert should_run(datetime(2026, 1, 15, 13, 5, tzinfo=UTC))
    assert not should_run(datetime(2026, 1, 15, 12, 5, tzinfo=UTC))
    assert should_run(datetime(2026, 7, 15, 7, 0, tzinfo=CHICAGO))
    assert should_run(datetime(2026, 7, 15, 12, 5, tzinfo=UTC))
    assert not should_run(datetime(2026, 7, 15, 13, 5, tzinfo=UTC))


def test_do_not_contact_blocks_send_words_approve_uses():
    assert do_not_contact_message({"outreach_status": "Do Not Contact", "email": "a@b.co"})
    hidden = {"status": "Needs research", "status_raw": "Do Not Contact", "email": "a@b.co"}
    assert do_not_contact_message(hidden)
    assert do_not_contact_message({"status": "do_not_contact"})
    assert do_not_contact_message({"email": "a@b.co", "name": "Pat"}) is None


def test_send_refuses_do_not_contact_before_gmail(client, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "pw")
    sent = {}

    class Svc:
        def get(self, _opp_id):
            return {
                "id": "rec1",
                "email": "lead@example.com",
                "outreach_status": "Do Not Contact",
                "draft_outreach_body": "Hello",
                "name": "Pat",
            }

        def update_fields(self, *_args, **_kwargs):
            raise AssertionError("a refused send must not write the lead")

    def boom(*_args, **_kwargs):
        sent["yes"] = True
        return {"ok": True}

    monkeypatch.setattr("server.get_opportunity_service", lambda: Svc())
    monkeypatch.setattr("services.gmail_send_service.send_email", boom)
    response = client.post(
        "/api/opportunities/rec1/send-email",
        headers={"X-App-Password": "pw"},
        json={"body": "Hello", "subject": "Hi"},
    )
    assert response.status_code == 409
    assert "Do Not Contact" in response.json()["detail"]
    assert "yes" not in sent


def test_send_still_sends_when_ryan_taps_and_the_lead_is_not_banned(client, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "pw")
    sent = {}

    class Svc:
        def get(self, _opp_id):
            return {
                "id": "rec2",
                "email": "pat@geauxmail.net",
                "outreach_status": "Not sent",
                "draft_outreach_body": "Hello from the draft",
                "name": "Pat",
                "outreach_attempt": 0,
            }

        def update_fields(self, _opp_id, updates):
            return {"id": "rec2", **updates}

    def fake_send(to_email, subject, text_body, include_photo=True):
        sent["to"] = to_email
        sent["body"] = text_body
        return {"ok": True, "to": to_email, "subject": subject}

    monkeypatch.setattr("server.get_opportunity_service", lambda: Svc())
    monkeypatch.setattr("services.gmail_send_service.send_email", fake_send)
    response = client.post(
        "/api/opportunities/rec2/send-email",
        headers={"X-App-Password": "pw"},
        json={"body": "Hello from the screen", "subject": "Hi"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert sent["to"] == "pat@geauxmail.net"
    assert sent["body"] == "Hello from the screen"
