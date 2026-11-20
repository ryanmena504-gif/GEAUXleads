"""Outbound calls and texts: password, guards, hours, STOP, and the Activity Log.

Twilio is faked. These tests do not place a call or send a text.
"""
from __future__ import annotations

import logging
from datetime import datetime
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from services import outbound_call_service as calls
from services import outbound_contact as contact
from services import outbound_sms_service as texts

CHICAGO = ZoneInfo("America/Chicago")
TOKEN = "test-auth-token"
BASE = "https://geauxleads.onrender.com"
INSIDE = datetime(2026, 11, 20, 10, 0, tzinfo=CHICAGO)  # Friday 10:00am
AUTH = {"x-app-password": "pw"}


def lead(**extra):
    row = {
        "id": "recLEAD",
        "name": "Magazine Bath",
        "decision_maker": "Jane Doe",
        "phone": "504-555-0142",
        "source": "Website",
        "status": "Ready",
        "notes": "",
        "activity_log_raw": "",
    }
    row.update(extra)
    return row


class _Result:
    def __init__(self, sid, status="queued"):
        self.sid = sid
        self.status = status


class _Bucket:
    def __init__(self, sink, sid):
        self.sink = sink
        self.sid = sid

    def create(self, **kwargs):
        self.sink.append(kwargs)
        return _Result(self.sid)


class FakeTwilio:
    def __init__(self):
        self.sent = []
        self.dialed = []
        self.messages = _Bucket(self.sent, "SM123")
        self.calls = _Bucket(self.dialed, "CA123")


class Journal:
    def __init__(self, rows):
        self.leads = {}
        for row in rows:
            item = dict(row)
            item.setdefault("activity_log_raw", "")
            item.setdefault("notes", "")
            self.leads[item["id"]] = item

    def get(self, lead_id):
        row = self.leads.get(lead_id)
        return dict(row) if row else None

    def add_activity(self, lead_id, type_, note):
        row = self.leads[lead_id]
        line = f"2026-11-20T16:00:00+00:00 | {type_} | {note}"
        current = row["activity_log_raw"]
        row["activity_log_raw"] = f"{current}\n{line}".strip()
        return dict(row)

    def update_fields(self, lead_id, updates):
        self.leads[lead_id].update(updates)
        return dict(self.leads[lead_id])

    def all(self):
        return [dict(row) for row in self.leads.values()]


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC" + "1" * 32)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+15042300550")
    monkeypatch.setenv("OWNER_PHONE", "+15045550199")
    monkeypatch.setenv("PUBLIC_BACKEND_URL", BASE)
    monkeypatch.setenv("APP_PASSWORD", "pw")
    for name in (
        "LEAD_NOTIFICATION_PHONE",
        "MISSED_CALL_NOTIFY_NUMBER",
        "MISSED_CALL_FROM_NUMBER",
        "MISSED_CALL_VOICE",
        "MISSED_CALL_VOICE_LANGUAGE",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    monkeypatch.setattr(contact, "current_time", lambda: INSIDE)


@pytest.fixture
def fake_twilio(monkeypatch):
    client = FakeTwilio()
    monkeypatch.setattr(contact, "twilio_client", lambda: client)
    return client


@pytest.fixture
def client(env, monkeypatch):
    monkeypatch.setenv("AIRTABLE_ENABLED", "false")
    monkeypatch.setenv("AIRTABLE_WEBHOOK_ENABLED", "false")
    from services.opportunity_service import reset_opportunity_service
    reset_opportunity_service()
    from server import app
    with TestClient(app) as test_client:
        yield test_client


def _use(monkeypatch, journal):
    monkeypatch.setattr("server.get_opportunity_service", lambda: journal)


def _sign(url, params):
    return RequestValidator(TOKEN).compute_signature(url, params)


# ---------------------------------------------------------------- guards
def test_bridge_is_allowed_on_a_permit_lead_and_a_recorded_message_is_not():
    permit = lead(source="permit", sms_permission="")
    contact.assert_call_allowed(permit, "bridge", INSIDE)
    with pytest.raises(contact.ContactRefused) as blocked:
        contact.assert_call_allowed(permit, "message", INSIDE)
    assert blocked.value.code == "needs_consent"
    with pytest.raises(contact.ContactRefused) as text:
        contact.assert_text_allowed(permit, INSIDE)
    assert text.value.code == "needs_consent"


def test_public_record_source_needs_consent_for_a_text_and_not_for_a_bridge_call():
    row = lead(source="Orleans Parish assessor public record")
    contact.assert_call_allowed(row, "bridge", INSIDE)
    with pytest.raises(contact.ContactRefused) as blocked:
        contact.assert_text_allowed(row, INSIDE)
    assert blocked.value.code == "needs_consent"


def test_consent_flag_and_a_reply_allow_the_text():
    contact.assert_text_allowed(lead(source="permit", sms_permission="Yes"), INSIDE)
    contact.assert_text_allowed(lead(source="permit", outreach_status="Replied"), INSIDE)


def test_opt_out_and_do_not_contact_block_both_channels():
    for row in (
        lead(status="Do Not Contact"),
        lead(risk_flags=["Homeowner opted out"]),
        lead(do_not_call=True),
        lead(sms_permission="Opted out"),
    ):
        for check in (
            lambda item: contact.assert_call_allowed(item, "bridge", INSIDE),
            lambda item: contact.assert_text_allowed(item, INSIDE),
        ):
            with pytest.raises(contact.ContactRefused) as blocked:
                check(row)
            assert blocked.value.code == "opted_out"


@pytest.mark.parametrize(
    "when,call_ok,text_ok",
    [
        (datetime(2026, 11, 23, 8, 59, tzinfo=CHICAGO), False, False),  # Monday 8:59am
        (datetime(2026, 11, 23, 9, 0, tzinfo=CHICAGO), True, True),      # Monday 9:00am
        (datetime(2026, 11, 20, 17, 59, tzinfo=CHICAGO), True, True),    # Friday 5:59pm
        (datetime(2026, 11, 20, 18, 0, tzinfo=CHICAGO), False, True),    # Friday 6:00pm
        (datetime(2026, 11, 20, 19, 0, tzinfo=CHICAGO), False, True),    # Friday 7:00pm
        (datetime(2026, 11, 21, 19, 59, tzinfo=CHICAGO), False, True),   # Saturday 7:59pm
        (datetime(2026, 11, 21, 20, 0, tzinfo=CHICAGO), False, False),   # Saturday 8:00pm
        (datetime(2026, 11, 22, 11, 0, tzinfo=CHICAGO), False, False),   # Sunday
    ],
)
def test_call_window_ends_at_6_and_text_window_ends_at_8(when, call_ok, text_ok):
    row = lead()
    if call_ok:
        contact.assert_call_allowed(row, "bridge", when)
    else:
        with pytest.raises(contact.ContactRefused) as blocked:
            contact.assert_call_allowed(row, "bridge", when)
        assert blocked.value.code == "outside_calling_window"
    if text_ok:
        contact.assert_text_allowed(row, when)
    else:
        with pytest.raises(contact.ContactRefused) as blocked:
            contact.assert_text_allowed(row, when)
        assert blocked.value.code == "outside_texting_window"


def test_hours_follow_the_lead_timezone():
    # 5:30pm in Chicago is 6:30pm in New York: too late to call, still fine to text.
    now = datetime(2026, 11, 20, 17, 30, tzinfo=CHICAGO)
    row = lead(timezone="America/New_York")
    with pytest.raises(contact.ContactRefused) as blocked:
        contact.assert_call_allowed(row, "bridge", now)
    assert blocked.value.code == "outside_calling_window"
    contact.assert_text_allowed(row, now)
    # 8:30am in Chicago is 9:30am in New York, so a call is allowed.
    early = datetime(2026, 11, 20, 8, 30, tzinfo=CHICAGO)
    contact.assert_call_allowed(row, "bridge", early)


def test_stop_line_is_added_once_and_a_prompt_is_refused():
    once = contact.ensure_stop_line("Hi Jane.")
    assert once.endswith(contact.STOP_LINE)
    assert contact.ensure_stop_line(once).count(contact.STOP_LINE) == 1
    long = contact.ensure_stop_line("A" * 2000)
    assert len(long) <= 1600 and long.endswith(contact.STOP_LINE)
    with pytest.raises(contact.ContactRefused) as blocked:
        texts.prepare_body("You are a lead-research assistant. Write a cold text.")
    assert blocked.value.code == "unsafe_body"
    with pytest.raises(contact.ContactRefused) as empty:
        texts.prepare_body("  ")
    assert empty.value.code == "empty_body"


def test_stop_and_start_keywords():
    assert contact.inbound_keyword("STOP") == "stop"
    assert contact.inbound_keyword("Please STOP texting me") == "stop"
    assert contact.inbound_keyword("UNSUBSCRIBE") == "stop"
    assert contact.inbound_keyword("START") == "start"
    assert contact.inbound_keyword("YES") == "start"
    assert contact.inbound_keyword("yes Thursday works") is None
    assert contact.inbound_keyword("unstoppable crew") is None


def test_activity_note_drops_a_status_that_is_not_a_status(env):
    note = contact.call_note(mode="bridge", sid="CA123", status=TOKEN, duration="42")
    assert TOKEN not in note
    assert "status=unknown" in note
    assert "duration=42s" in note
    text = contact.text_note(sid="SM123", status=TOKEN, body="Hi Jane")
    assert TOKEN not in text
    assert "status=unknown" in text
    assert "body=Hi Jane" in text


# ---------------------------------------------------------------- twiml
def test_message_uses_the_greeting_voice_and_leaves_voicemail_for_a_machine(env, monkeypatch):
    human = calls.message_twiml(lead(), "human")
    say = ElementTree.fromstring(human).find("Gather/Say")
    assert say is not None
    assert say.get("voice") == "Polly.Joanna-Generative"
    assert say.get("language") == "en-US"
    assert "Press 1" in (say.text or "")
    assert "Ryan's assistant" in (say.text or "")

    machine = calls.message_twiml(lead(), "machine_end_beep")
    assert "<Gather" not in machine
    assert "five zero four, two three zero, zero five five zero" in machine
    monkeypatch.setenv("MISSED_CALL_VOICE", "Polly.Ruth-Generative")
    ruth = ElementTree.fromstring(calls.message_twiml(lead(), "human")).find("Gather/Say")
    assert ruth is not None and ruth.get("voice") == "Polly.Ruth-Generative"


def test_bridge_dials_the_lead_with_the_shop_caller_id_and_hangs_up_on_voicemail(env):
    human = calls.bridge_twiml(lead(), "human")
    dial = ElementTree.fromstring(human).find("Dial")
    assert dial is not None
    assert dial.get("callerId") == "+15042300550"
    assert dial.find("Number").text == "+15045550142"
    machine = calls.bridge_twiml(lead(), "machine_start")
    assert "<Dial" not in machine and "+15045550142" not in machine


def test_press_one_dials_ryan_and_anything_else_hangs_up(env):
    connected = calls.gather_twiml(lead(), "1")
    number = ElementTree.fromstring(connected).find("Dial/Number")
    assert number is not None and number.text == "+15045550199"
    assert "outbound/whisper" in (number.get("url") or "")
    assert "<Dial" not in calls.gather_twiml(lead(), "9")
    whispered = calls.whisper_twiml(lead(decision_maker="Tom & Jerry"))
    assert "Tom &amp; Jerry" in whispered


def test_place_call_rings_ryan_first_and_a_message_rings_the_lead(env, fake_twilio, monkeypatch):
    bridge = calls.place_call(lead(), "bridge")
    assert bridge["sid"] == "CA123"
    dialed = fake_twilio.dialed[0]
    assert dialed["to"] == "+15045550199"
    assert dialed["from_"] == "+15042300550"
    assert dialed["machine_detection"] == "Enable"
    assert "outbound/bridge" in dialed["url"]

    calls.place_call(lead(), "message")
    message = fake_twilio.dialed[1]
    assert message["to"] == "+15045550142"
    assert message["machine_detection"] == "DetectMessageEnd"
    assert "outbound/message" in message["url"]

    monkeypatch.setenv("LEAD_NOTIFICATION_PHONE", "+15045550111")
    calls.place_call(lead(), "bridge")
    assert fake_twilio.dialed[-1]["to"] == "+15045550199"
    monkeypatch.delenv("OWNER_PHONE")
    calls.place_call(lead(), "bridge")
    assert fake_twilio.dialed[-1]["to"] == "+15045550111"


# ---------------------------------------------------------------- http
def test_call_and_text_require_the_app_password(client, fake_twilio, monkeypatch):
    journal = Journal([lead()])
    _use(monkeypatch, journal)
    assert client.post("/api/opportunities/recLEAD/call", json={}).status_code == 401
    assert client.post("/api/opportunities/recLEAD/text", json={"body": "Hi Jane"}).status_code == 401
    assert fake_twilio.dialed == [] and fake_twilio.sent == []


def test_script_texts_with_x_app_password_and_logs_body_sid_status(client, fake_twilio, monkeypatch):
    journal = Journal([lead()])
    _use(monkeypatch, journal)
    response = client.post(
        "/api/opportunities/recLEAD/text",
        headers=AUTH,
        json={"body": "Hi Jane — Ryan at The Shirtless Handyman."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["message_sid"] == "SM123"
    assert body["activity_logged"] is True
    assert body["body"].endswith("Reply STOP to opt out")
    assert TOKEN not in response.text
    assert fake_twilio.sent[0]["from_"] == "+15042300550"
    assert fake_twilio.sent[0]["to"] == "+15045550142"
    log_line = journal.leads["recLEAD"]["activity_log_raw"]
    assert "2026-11-20T16:00:00+00:00 | text |" in log_line
    assert "sid=SM123" in log_line and "status=queued" in log_line
    assert "Hi Jane" in log_line and "Reply STOP to opt out" in log_line


def test_bridge_call_logs_the_sid_and_a_permit_message_is_refused(client, fake_twilio, monkeypatch):
    journal = Journal([
        lead(),
        lead(id="recPERMIT", source="permit", sms_permission=""),
    ])
    _use(monkeypatch, journal)
    ok = client.post("/api/opportunities/recLEAD/call", headers=AUTH, json={})
    assert ok.status_code == 200
    assert ok.json()["mode"] == "bridge" and ok.json()["call_sid"] == "CA123"
    assert "sid=CA123" in journal.leads["recLEAD"]["activity_log_raw"]
    assert fake_twilio.dialed[0]["to"] == "+15045550199"

    refused = client.post(
        "/api/opportunities/recPERMIT/call",
        headers=AUTH,
        json={"mode": "message"},
    )
    assert refused.status_code == 403
    assert refused.json()["detail"]["error"] == "needs_consent"
    assert len(fake_twilio.dialed) == 1

    bridged = client.post(
        "/api/opportunities/recPERMIT/call",
        headers=AUTH,
        json={"mode": "bridge"},
    )
    assert bridged.status_code == 200
    assert len(fake_twilio.dialed) == 2


def test_text_is_refused_for_a_permit_without_consent_and_allowed_after_yes(client, fake_twilio, monkeypatch):
    journal = Journal([lead(id="recPERMIT", source="permit", sms_permission="")])
    _use(monkeypatch, journal)
    refused = client.post(
        "/api/opportunities/recPERMIT/text",
        headers=AUTH,
        json={"body": "Hello from the shop."},
    )
    assert refused.status_code == 403
    assert refused.json()["detail"]["error"] == "needs_consent"
    assert fake_twilio.sent == []

    journal.leads["recPERMIT"]["sms_permission"] = "Yes"
    allowed = client.post(
        "/api/opportunities/recPERMIT/text",
        headers=AUTH,
        json={"body": "Hello from the shop."},
    )
    assert allowed.status_code == 200
    assert len(fake_twilio.sent) == 1


def test_evening_allows_a_text_and_refuses_a_call(client, fake_twilio, monkeypatch):
    journal = Journal([lead()])
    _use(monkeypatch, journal)
    monkeypatch.setattr(contact, "current_time", lambda: datetime(2026, 11, 20, 19, 0, tzinfo=CHICAGO))
    text = client.post(
        "/api/opportunities/recLEAD/text",
        headers=AUTH,
        json={"body": "Hi Jane — still free this week?"},
    )
    assert text.status_code == 200
    call = client.post("/api/opportunities/recLEAD/call", headers=AUTH, json={"mode": "bridge"})
    assert call.status_code == 403
    assert call.json()["detail"]["error"] == "outside_calling_window"
    assert len(fake_twilio.dialed) == 0


def test_stop_webhook_marks_the_lead_and_a_later_text_is_refused(client, fake_twilio, monkeypatch):
    journal = Journal([lead()])
    _use(monkeypatch, journal)
    params = {"From": "+15045550142", "Body": "Please STOP", "MessageSid": "SMin1"}
    url = BASE + "/api/twilio/sms/inbound"
    bad = client.post("/api/twilio/sms/inbound", data=params)
    assert bad.status_code == 403
    assert journal.leads["recLEAD"]["notes"] == ""

    ok = client.post(
        "/api/twilio/sms/inbound",
        data=params,
        headers={"X-Twilio-Signature": _sign(url, params)},
    )
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("application/xml")
    assert contact.OPT_OUT_MARKER in journal.leads["recLEAD"]["notes"]
    assert "sms_opt_out" in journal.leads["recLEAD"]["activity_log_raw"]
    assert TOKEN not in journal.leads["recLEAD"]["activity_log_raw"]

    again = client.post(
        "/api/twilio/sms/inbound",
        data=params,
        headers={"X-Twilio-Signature": _sign(url, params)},
    )
    assert again.status_code == 200
    assert journal.leads["recLEAD"]["activity_log_raw"].count("sms_opt_out") == 1

    refused = client.post(
        "/api/opportunities/recLEAD/text",
        headers=AUTH,
        json={"body": "Hi Jane — one more note."},
    )
    assert refused.status_code == 403
    assert refused.json()["detail"]["error"] == "opted_out"
    assert fake_twilio.sent == []

    start = {"From": "+15045550142", "Body": "START", "MessageSid": "SMin2"}
    started = client.post(
        "/api/twilio/sms/inbound",
        data=start,
        headers={"X-Twilio-Signature": _sign(url, start)},
    )
    assert started.status_code == 200
    assert contact.OPT_OUT_MARKER not in journal.leads["recLEAD"]["notes"]
    resumed = client.post(
        "/api/opportunities/recLEAD/text",
        headers=AUTH,
        json={"body": "Hi Jane — thanks for the yes."},
    )
    assert resumed.status_code == 200
    assert len(fake_twilio.sent) == 1


def test_status_callback_logs_duration_and_a_repeat_does_not(client, monkeypatch):
    journal = Journal([lead()])
    _use(monkeypatch, journal)
    params = {"CallSid": "CA999", "CallStatus": "completed", "CallDuration": "42"}
    url = BASE + "/api/twilio/voice/outbound/status?lead_id=recLEAD&mode=bridge"
    headers = {"X-Twilio-Signature": _sign(url, params)}
    path = "/api/twilio/voice/outbound/status?lead_id=recLEAD&mode=bridge"
    first = client.post(path, data=params, headers=headers)
    assert first.status_code == 200 and first.json()["logged"] is True
    line = journal.leads["recLEAD"]["activity_log_raw"]
    assert "sid=CA999" in line and "status=completed" in line and "duration=42s" in line
    assert "mode=bridge" in line
    second = client.post(path, data=params, headers=headers)
    assert second.status_code == 200
    assert journal.leads["recLEAD"]["activity_log_raw"].count("status=completed") == 1


def test_text_status_callback_logs_delivery(client, monkeypatch):
    journal = Journal([lead()])
    _use(monkeypatch, journal)
    params = {"MessageSid": "SM999", "MessageStatus": "delivered"}
    url = BASE + "/api/twilio/sms/status?lead_id=recLEAD"
    response = client.post(
        "/api/twilio/sms/status?lead_id=recLEAD",
        data=params,
        headers={"X-Twilio-Signature": _sign(url, params)},
    )
    assert response.status_code == 200
    line = journal.leads["recLEAD"]["activity_log_raw"]
    assert "sid=SM999" in line and "status=delivered" in line
    assert TOKEN not in line


def test_signed_bridge_webhook_hangs_up_when_ryan_gets_voicemail(client, monkeypatch):
    journal = Journal([lead()])
    _use(monkeypatch, journal)
    params = {"CallSid": "CA123", "AnsweredBy": "machine_start"}
    url = BASE + "/api/twilio/voice/outbound/bridge?lead_id=recLEAD&mode=bridge"
    response = client.post(
        "/api/twilio/voice/outbound/bridge?lead_id=recLEAD&mode=bridge",
        data=params,
        headers={"X-Twilio-Signature": _sign(url, params)},
    )
    assert response.status_code == 200
    assert "<Hangup" in response.text and "+15045550142" not in response.text
    assert "owner_voicemail" in journal.leads["recLEAD"]["activity_log_raw"]


def test_a_bad_from_number_is_not_echoed_and_a_twilio_error_does_not_log_the_token(
    client, monkeypatch, caplog,
):
    journal = Journal([lead()])
    _use(monkeypatch, journal)
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "not-a-number")
    monkeypatch.delenv("MISSED_CALL_FROM_NUMBER", raising=False)
    missing = client.post(
        "/api/opportunities/recLEAD/text",
        headers=AUTH,
        json={"body": "Hi Jane — checking in."},
    )
    assert missing.status_code == 503
    assert "not-a-number" not in missing.text
    assert "TWILIO_FROM_NUMBER" in missing.text
    assert TOKEN not in missing.text

    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+15042300550")

    class Boom(Exception):
        status = 401
        code = 20003

        def __str__(self):
            return "token " + TOKEN

    class Bad:
        def create(self, **kwargs):
            raise Boom()

    class BadClient:
        messages = Bad()
        calls = Bad()

    monkeypatch.setattr(contact, "twilio_client", lambda: BadClient())
    with caplog.at_level(logging.WARNING):
        failed = client.post(
            "/api/opportunities/recLEAD/text",
            headers=AUTH,
            json={"body": "Hi Jane — checking in."},
        )
    assert failed.status_code == 502
    assert TOKEN not in failed.text
    assert TOKEN not in caplog.text
    assert journal.leads["recLEAD"]["activity_log_raw"] == ""
