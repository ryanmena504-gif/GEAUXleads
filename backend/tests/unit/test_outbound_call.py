"""Outbound voice: password, compliance, calling window, TwiML, activity log.

Twilio and Airtable are fakes. No credential value is written to a log line
or a response.
"""
from __future__ import annotations

from datetime import datetime
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from services import outbound_call_service as ocs
from services.call_hours import within_calling_hours, zone_for_phone

CHICAGO = ZoneInfo("America/Chicago")
TOKEN = "super-secret-token"
SID = "CA" + "ab" * 16
FROM = "+15042300550"
OWNER = "+15045550199"
LEAD = "+15045550142"
PUBLIC = "http://testserver"


class FakeCall:
    def __init__(self):
        self.sid = SID
        self.status = "queued"


class FakeClient:
    def __init__(self):
        self.created = []
        outer = self

        class Calls:
            def create(self, **kwargs):
                outer.created.append(kwargs)
                return FakeCall()

        self.calls = Calls()


class LogSvc:
    def __init__(self, lead):
        self.lead = dict(lead)
        self.lead.setdefault("id", "rec1")
        self.lead.setdefault("activity_log_raw", "")
        self.notes = []

    def get(self, opp_id):
        if opp_id != self.lead["id"]:
            return None
        return dict(self.lead)

    def add_activity(self, opp_id, type_, note):
        if opp_id != self.lead["id"]:
            return None
        line = f"2026-11-20T16:00:00+00:00 | {type_} | {note}"
        current = (self.lead.get("activity_log_raw") or "").strip()
        self.lead["activity_log_raw"] = f"{current}\n{line}".strip()
        self.notes.append((type_, note))
        return dict(self.lead)


def _lead(**extra):
    base = {
        "id": "rec1",
        "name": "Magazine bath",
        "decision_maker": "Jane Doe",
        "phone": "(504) 555-0142",
        "source": "Referral",
        "outreach_status": "Not sent",
    }
    base.update(extra)
    return base


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC" + "0" * 32)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("TWILIO_FROM_NUMBER", FROM)
    monkeypatch.setenv("OWNER_PHONE", OWNER)
    monkeypatch.setenv("PUBLIC_BACKEND_URL", PUBLIC)
    monkeypatch.delenv("MISSED_CALL_VOICE", raising=False)
    monkeypatch.delenv("MISSED_CALL_VOICE_LANGUAGE", raising=False)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AIRTABLE_ENABLED", "false")
    monkeypatch.setenv("AIRTABLE_WEBHOOK_ENABLED", "false")
    monkeypatch.setenv("APP_PASSWORD", "pw")
    from services.opportunity_service import reset_opportunity_service
    reset_opportunity_service()
    from server import app
    with TestClient(app) as test_client:
        yield test_client


def _patch_client(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(ocs, "_client", lambda: fake)
    return fake


def _friday(hour, minute=0):
    return datetime(2026, 11, 20, hour, minute, tzinfo=CHICAGO)


# ---------------------------------------------------------------- hours
def test_window_is_monday_through_saturday_nine_to_six_local():
    phone = "5045550142"
    assert zone_for_phone(phone) == CHICAGO
    assert within_calling_hours(_friday(9, 0), phone)
    assert within_calling_hours(_friday(17, 59), phone)
    assert not within_calling_hours(_friday(8, 59), phone)
    assert not within_calling_hours(_friday(18, 0), phone)
    saturday = datetime(2026, 11, 14, 17, 30, tzinfo=CHICAGO)
    sunday = datetime(2026, 11, 15, 10, 0, tzinfo=CHICAGO)
    assert within_calling_hours(saturday, phone)
    assert not within_calling_hours(sunday, phone)


def test_pacific_and_hawaii_use_the_lead_clock_not_chicago():
    # 9:30am Chicago in November is 7:30am Pacific and 5:30am Hawaii.
    morning = _friday(9, 30)
    assert not within_calling_hours(morning, "4155550100")
    assert not within_calling_hours(morning, "8085550100")
    # 11:30am Chicago is 9:30am Pacific.
    assert within_calling_hours(_friday(11, 30), "4155550100")
    # Noon Chicago is 8:00am Hawaii. 1:30pm Chicago is 9:30am Hawaii.
    assert not within_calling_hours(_friday(12, 0), "8085550100")
    assert within_calling_hours(_friday(13, 30), "8085550100")


def test_unknown_area_code_only_dials_inside_every_us_zone():
    unknown = "2005550100"
    assert zone_for_phone(unknown) is None
    # Winter: 12:30pm Chicago is 8:30am Hawaii. 1:30pm is 9:30am Hawaii
    # and still before 6pm Eastern. 5:00pm Chicago is 6:00pm Eastern.
    assert not within_calling_hours(_friday(12, 30), unknown)
    assert within_calling_hours(_friday(13, 30), unknown)
    assert not within_calling_hours(_friday(17, 0), unknown)
    summer_early = datetime(2026, 7, 15, 13, 30, tzinfo=CHICAGO)
    summer_open = datetime(2026, 7, 15, 14, 30, tzinfo=CHICAGO)
    assert not within_calling_hours(summer_early, unknown)
    assert within_calling_hours(summer_open, unknown)


# ---------------------------------------------------------------- guards
def test_message_mode_refuses_a_permit_lead_without_consent(env, monkeypatch):
    fake = _patch_client(monkeypatch)
    monkeypatch.setattr(ocs, "_now", lambda: _friday(10))
    lead = _lead(source="Building permit")
    with pytest.raises(ocs.CallBlocked) as caught:
        ocs.place_call(lead, "message", LogSvc(lead))
    assert caught.value.status_code == 409
    assert "consent" in caught.value.detail
    assert fake.created == []


def test_bridge_mode_allows_the_same_permit_lead(env, monkeypatch):
    fake = _patch_client(monkeypatch)
    monkeypatch.setattr(ocs, "_now", lambda: _friday(10))
    lead = _lead(source="public record")
    svc = LogSvc(lead)
    result = ocs.place_call(lead, "bridge", svc)
    assert result["ok"] is True
    assert result["mode"] == "bridge"
    assert result["call_sid"] == SID
    assert len(fake.created) == 1
    call = fake.created[0]
    assert call["to"] == OWNER
    assert call["from_"] == FROM
    assert "machine_detection" not in call
    assert "mode=bridge" in call["url"]
    assert svc.notes == [("call", f"mode=bridge sid={SID} status=queued")]
    assert TOKEN not in str(svc.notes)
    assert TOKEN not in str(call)


def test_message_mode_dials_the_lead_and_asks_twilio_to_detect_a_machine(env, monkeypatch):
    fake = _patch_client(monkeypatch)
    monkeypatch.setattr(ocs, "_now", lambda: _friday(10))
    lead = _lead(source="Building permit", sms_permission="Yes")
    ocs.place_call(lead, "message", LogSvc(lead))
    call = fake.created[0]
    assert call["to"] == LEAD
    assert call["from_"] == FROM
    assert call["machine_detection"] == "DetectMessageEnd"
    assert "mode=message" in call["status_callback"]


def test_public_record_sale_and_assessor_need_consent_for_message_mode(env):
    for source in ("Sale listing", "Tax roll", "Assessor"):
        lead = _lead(source=source)
        assert ocs.message_blocked_reason(lead)
    allowed = _lead(source="Instagram")
    assert ocs.message_blocked_reason(allowed) is None
    consented = _lead(source="Permit", call_consent="yes")
    assert ocs.message_blocked_reason(consented) is None


def test_opt_out_blocks_both_modes_and_does_not_call_twilio(env, monkeypatch):
    fake = _patch_client(monkeypatch)
    monkeypatch.setattr(ocs, "_now", lambda: _friday(10))
    for extra in (
        {"outreach_status": "Do Not Contact"},
        {"status": "do_not_contact"},
        {"risk_flags": ["Opted out"]},
        {"do_not_call": "yes"},
        {"suppressed": True},
    ):
        lead = _lead(**extra)
        for mode in ("bridge", "message"):
            with pytest.raises(ocs.CallBlocked) as caught:
                ocs.place_call(lead, mode, LogSvc(lead))
            assert caught.value.status_code == 409
    assert fake.created == []


def test_outside_hours_and_sunday_place_nothing(env, monkeypatch):
    fake = _patch_client(monkeypatch)
    lead = _lead()
    monkeypatch.setattr(ocs, "_now", lambda: _friday(8, 30))
    with pytest.raises(ocs.CallBlocked) as early:
        ocs.place_call(lead, "bridge", LogSvc(lead))
    assert early.value.status_code == 409
    assert "calling hours" in early.value.detail.lower()
    monkeypatch.setattr(ocs, "_now", lambda: datetime(2026, 11, 15, 11, tzinfo=CHICAGO))
    with pytest.raises(ocs.CallBlocked):
        ocs.place_call(lead, "message", LogSvc(lead))
    assert fake.created == []


def test_sample_style_ids_with_underscores_can_be_called(env, monkeypatch):
    fake = _patch_client(monkeypatch)
    monkeypatch.setattr(ocs, "_now", lambda: _friday(10))
    lead = _lead(id="opp_015", phone="504-555-0122")
    result = ocs.place_call(lead, "bridge", LogSvc(lead))
    assert result["call_sid"] == SID
    assert fake.created[0]["url"].endswith("lead_id=opp_015&mode=bridge")


def test_a_homeowner_reminder_is_not_an_opt_out(env, monkeypatch):
    fake = _patch_client(monkeypatch)
    monkeypatch.setattr(ocs, "_now", lambda: _friday(10))
    lead = _lead(dnc_check_required=True, contact_source="homeowner")
    result = ocs.place_call(lead, "bridge", LogSvc(lead))
    assert result["call_sid"] == SID
    assert len(fake.created) == 1


def test_missing_settings_names_do_not_include_values(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TOKEN)
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_FROM_NUMBER", raising=False)
    monkeypatch.delenv("MISSED_CALL_FROM_NUMBER", raising=False)
    monkeypatch.delenv("OWNER_PHONE", raising=False)
    monkeypatch.delenv("LEAD_NOTIFICATION_PHONE", raising=False)
    monkeypatch.delenv("MISSED_CALL_NOTIFY_NUMBER", raising=False)
    monkeypatch.delenv("PUBLIC_BACKEND_URL", raising=False)
    missing = ocs.missing_settings()
    text = ", ".join(missing)
    assert "TWILIO_ACCOUNT_SID" in text
    assert "TWILIO_FROM_NUMBER" in text
    assert "OWNER_PHONE" in text
    assert "PUBLIC_BACKEND_URL" in text
    assert TOKEN not in text


def test_status_callback_logs_status_and_duration_once(env):
    lead = _lead()
    svc = LogSvc(lead)
    params = {"CallSid": SID, "CallStatus": "completed", "CallDuration": "42"}
    first = ocs.record_status(svc, "rec1", "bridge", params)
    second = ocs.record_status(svc, "rec1", "bridge", params)
    assert first["logged"] is True and second["logged"] is True
    assert svc.notes == [("call", f"mode=bridge sid={SID} status=completed duration=42")]
    assert TOKEN not in svc.lead["activity_log_raw"]


def test_twilio_errors_do_not_log_the_auth_token(env, monkeypatch, caplog):
    class Boom:
        calls = None

        def __init__(self):
            self.calls = self

        def create(self, **kwargs):
            raise RuntimeError(f"auth failed {TOKEN}")

    monkeypatch.setattr(ocs, "_client", lambda: Boom())
    monkeypatch.setattr(ocs, "_now", lambda: _friday(10))
    lead = _lead()
    with caplog.at_level("WARNING"):
        with pytest.raises(ocs.CallFailed) as caught:
            ocs.place_call(lead, "bridge", LogSvc(lead))
    assert TOKEN not in caught.value.detail
    assert TOKEN not in caplog.text


# ---------------------------------------------------------------- TwiML voice
def _say_nodes(xml):
    root = ElementTree.fromstring(xml)
    return root.findall(".//Say")


def test_message_to_a_person_uses_the_greeting_voice_and_press_1(env):
    lead = _lead(source="Referral")
    xml = ocs.connect_twiml(lead, "message", "human")
    says = _say_nodes(xml)
    assert says
    assert says[0].get("voice") == "Polly.Joanna-Generative"
    assert says[0].get("language") == "en-US"
    assert "Ryan's assistant" in says[0].text
    assert "The Shirtless Handyman" in says[0].text
    gather = ElementTree.fromstring(xml).find("Gather")
    assert gather is not None
    assert "outbound-gather" in gather.get("action")
    assert "<Dial" not in xml


def test_machine_detection_leaves_voicemail_in_the_same_voice(env):
    lead = _lead()
    xml = ocs.connect_twiml(lead, "message", "machine_end_beep")
    says = _say_nodes(xml)
    assert len(says) == 1
    assert says[0].get("voice") == "Polly.Joanna-Generative"
    assert "Ryan's assistant" in says[0].text
    assert "504" in says[0].text
    assert "Gather" not in xml
    assert "Dial" not in xml
    assert "<Hangup/>" in xml


def test_press_1_connects_to_ryan_with_the_business_caller_id(env):
    lead = _lead()
    xml = ocs.gather_twiml(lead, "1")
    dial = ElementTree.fromstring(xml).find("Dial")
    assert dial is not None
    assert dial.get("callerId") == FROM
    assert dial.find("Number").text == OWNER
    assert "Polly.Joanna-Generative" in xml
    ignored = ocs.gather_twiml(lead, "2")
    assert "Dial" not in ignored


def test_bridge_connect_dials_the_lead_with_the_business_caller_id(env):
    lead = _lead(decision_maker="Jane & Doe")
    xml = ocs.connect_twiml(lead, "bridge", "")
    root = ElementTree.fromstring(xml)
    say = root.find("Say")
    assert say.get("voice") == "Polly.Joanna-Generative"
    assert "Jane" in say.text and "&" not in say.text
    dial = root.find("Dial")
    assert dial.get("callerId") == FROM
    assert dial.find("Number").text == LEAD


def test_opt_out_checked_again_before_twiml_speaks(env):
    lead = _lead(outreach_status="Do Not Contact")
    xml = ocs.connect_twiml(lead, "message", "human")
    assert "Gather" not in xml and "Dial" not in xml
    assert "Say" not in xml


# ---------------------------------------------------------------- route
def _signed(path, params):
    return RequestValidator(TOKEN).compute_signature(PUBLIC + path, params)


def test_place_call_requires_the_app_password(client, env, monkeypatch):
    fake = _patch_client(monkeypatch)
    monkeypatch.setattr(ocs, "_now", lambda: _friday(10))
    svc = LogSvc(_lead())
    monkeypatch.setattr("server.get_opportunity_service", lambda: svc)
    locked = client.post("/api/opportunities/rec1/call", json={"mode": "bridge"})
    assert locked.status_code == 401
    assert fake.created == []
    opened = client.post(
        "/api/opportunities/rec1/call",
        json={"mode": "bridge"},
        headers={"X-App-Password": "pw"},
    )
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert body["call_sid"] == SID
    assert body["mode"] == "bridge"
    assert TOKEN not in opened.text
    assert svc.notes[0][0] == "call"


def test_route_refuses_message_mode_for_a_permit_and_keeps_bridge(client, env, monkeypatch):
    fake = _patch_client(monkeypatch)
    monkeypatch.setattr(ocs, "_now", lambda: _friday(10))
    svc = LogSvc(_lead(source="Permit filed"))
    monkeypatch.setattr("server.get_opportunity_service", lambda: svc)
    headers = {"X-App-Password": "pw"}
    refused = client.post("/api/opportunities/rec1/call", json={"mode": "message"}, headers=headers)
    assert refused.status_code == 409
    assert "consent" in refused.json()["detail"]
    assert fake.created == []
    bridged = client.post("/api/opportunities/rec1/call", json={}, headers=headers)
    assert bridged.status_code == 200
    assert bridged.json()["mode"] == "bridge"
    assert fake.created[0]["to"] == OWNER


def test_route_refuses_a_call_outside_the_window(client, env, monkeypatch):
    fake = _patch_client(monkeypatch)
    monkeypatch.setattr(ocs, "_now", lambda: _friday(20))
    svc = LogSvc(_lead())
    monkeypatch.setattr("server.get_opportunity_service", lambda: svc)
    response = client.post(
        "/api/opportunities/rec1/call",
        json={"mode": "bridge"},
        headers={"X-App-Password": "pw"},
    )
    assert response.status_code == 409
    assert TOKEN not in response.text
    assert fake.created == []
    assert svc.notes == []


def test_status_callback_needs_a_twilio_signature_and_logs_duration(client, env, monkeypatch):
    svc = LogSvc(_lead())
    monkeypatch.setattr("server.get_opportunity_service", lambda: svc)
    path = f"/api/twilio/voice/outbound-status?lead_id=rec1&mode=bridge"
    params = {"CallSid": SID, "CallStatus": "completed", "CallDuration": "15"}
    bad = client.post(path, data=params, headers={"X-Twilio-Signature": "nope"})
    assert bad.status_code == 403
    assert svc.notes == []
    ok = client.post(path, data=params, headers={"X-Twilio-Signature": _signed(path, params)})
    assert ok.status_code == 204
    assert svc.notes == [("call", f"mode=bridge sid={SID} status=completed duration=15")]
    again = client.post(path, data=params, headers={"X-Twilio-Signature": _signed(path, params)})
    assert again.status_code == 204
    assert len(svc.notes) == 1
    assert TOKEN not in svc.lead["activity_log_raw"]


def test_connect_webhook_is_signed_and_speaks_with_joanna(client, env, monkeypatch):
    svc = LogSvc(_lead(source="Referral"))
    monkeypatch.setattr("server.get_opportunity_service", lambda: svc)
    path = "/api/twilio/voice/outbound-connect?lead_id=rec1&mode=message"
    params = {"CallSid": SID, "AnsweredBy": "human"}
    bad = client.post(path, data=params)
    assert bad.status_code == 403
    ok = client.post(path, data=params, headers={"X-Twilio-Signature": _signed(path, params)})
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("application/xml")
    assert 'voice="Polly.Joanna-Generative"' in ok.text
    assert "Press 1" in ok.text
    assert TOKEN not in ok.text


def test_other_routes_stay_on_the_password(client, env):
    assert client.get("/api/twilio/voice/outbound-status").status_code in (401, 405)
    assert client.post("/api/opportunities/rec1/call", json={"mode": "bridge"}).status_code == 401
