"""Missed-call text: signature gate, lead match, capped one-shot research,
one SMS. No network: Twilio sends, Perplexity, and Airtable are faked."""
from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from services import missed_call_service as mcs

CHICAGO = ZoneInfo("America/Chicago")
NOW = datetime(2026, 11, 13, 14, 5, tzinfo=CHICAGO)
TOKEN = "test-auth-token"
URL = "https://geauxleads.onrender.com/api/twilio/voice/missed-call"

LEADS = [
    {"id": "rec1", "name": "Bath remodel", "decision_maker": "Jane Doe",
     "project_address": "123 Magazine St", "project_type": "Residential",
     "status": "New", "phone": "(504) 555-0142"},
    {"id": "rec2", "name": "Other", "phone_alt": "985-555-0000 / 504-555-0199"},
]


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC" + "0" * 32)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("MISSED_CALL_FROM_NUMBER", "+15045550001")
    monkeypatch.setenv("MISSED_CALL_NOTIFY_NUMBER", "+15045559999")
    monkeypatch.setenv("MISSED_CALL_WEBHOOK_URL", URL)
    monkeypatch.delenv("MISSED_CALL_TWIML_MODE", raising=False)
    monkeypatch.delenv("MISSED_CALL_RESEARCH_DAILY_CAP", raising=False)


def _run(params, *, research=None, leads=LEADS, budget=None):
    sent = []

    async def load():
        return leads

    out = asyncio.run(mcs.handle_missed_call(
        params, load_leads=load, research=research,
        send=lambda body: sent.append(body) or "SM1",
        now=NOW, budget=budget or mcs.ResearchBudget(),
    ))
    return out, sent


# ------------------------------------------------------------ pure helpers
def test_caller_digits_normalizes_and_drops_hidden_numbers():
    assert mcs.caller_digits("+15045550142") == "5045550142"
    assert mcs.caller_digits("(504) 555-0142") == "5045550142"
    assert mcs.caller_digits("anonymous") is None
    assert mcs.caller_digits("+442071234567") is None
    assert mcs.caller_digits("") is None


def test_match_finds_contact_phone_and_a_second_number_in_one_cell():
    assert [o["id"] for o in mcs.match_leads("5045550142", LEADS)] == ["rec1"]
    assert [o["id"] for o in mcs.match_leads("5045550199", LEADS)] == ["rec2"]
    assert mcs.match_leads("5045551111", LEADS) == []
    assert mcs.match_leads(None, LEADS) == []


def test_parse_caller_line():
    assert mcs.parse_caller("Listed on Yelp.\nCALLER: Big Easy Plumbing LLC") == "Big Easy Plumbing LLC"
    assert mcs.parse_caller("Nothing found.\nCALLER: unknown") is None
    assert mcs.parse_caller("no marker") is None


def test_twiml_say_by_default_and_reject_when_asked(env, monkeypatch):
    assert "<Say>" in mcs.twiml_response() and "<Hangup/>" in mcs.twiml_response()
    monkeypatch.setenv("MISSED_CALL_TWIML_MODE", "reject")
    assert mcs.twiml_response().count("<Reject") == 1
    monkeypatch.setenv("MISSED_CALL_TWIML_MODE", "say")
    monkeypatch.setenv("MISSED_CALL_GREETING", "Tom & Jerry <hi>")
    assert "Tom &amp; Jerry &lt;hi&gt;" in mcs.twiml_response()


# ------------------------------------------------------------ the job
def test_known_lead_texts_ryan_without_research(env):
    called = []

    async def research(kind, query):
        called.append(query)
        return {"answer": "CALLER: x"}

    out, sent = _run({"From": "+15045550142", "CallSid": "CA1"}, research=research)
    assert called == []
    assert out["matched"] == 1 and out["sms_sid"] == "SM1"
    assert len(sent) == 1
    body = sent[0]
    assert "Missed call 2:05 PM CT from (504) 555-0142" in body
    assert "Jane Doe" in body and "123 Magazine St" in body
    assert "/lookup?phone=%2B15045550142" in body
    assert len(body) <= mcs.SMS_MAX_CHARS


def test_unknown_caller_gets_one_research_call_and_one_text(env):
    calls = []

    async def research(kind, query):
        calls.append((kind, query))
        return {"answer": "Google listing.\nCALLER: Big Easy Plumbing"}

    out, sent = _run({"From": "+15045551111", "CallerName": "BIG EASY PLMB"}, research=research)
    assert calls == [("caller_lookup", "+15045551111")]
    assert len(sent) == 1
    assert "Not in GEAUXleads" in sent[0]
    assert "Caller ID name: BIG EASY PLMB" in sent[0]
    assert "Web: Big Easy Plumbing" in sent[0]


def test_failed_research_is_not_retried_and_pauses_research_for_the_day(env):
    budget = mcs.ResearchBudget()
    calls = []

    async def research(kind, query):
        calls.append(query)
        raise RuntimeError("upstream 500")

    _, sent = _run({"From": "+15045551111"}, research=research, budget=budget)
    assert len(calls) == 1
    assert "Web lookup failed (not retried)" in sent[0]
    _, sent2 = _run({"From": "+15045552222"}, research=research, budget=budget)
    assert len(calls) == 1  # still one: paused after the failure
    assert "paused after a failed lookup" in sent2[0]


def test_daily_cap_and_same_number_reuse(env, monkeypatch):
    monkeypatch.setenv("MISSED_CALL_RESEARCH_DAILY_CAP", "1")
    budget = mcs.ResearchBudget()
    calls = []

    async def research(kind, query):
        calls.append(query)
        return {"answer": "CALLER: Acme Realty"}

    _run({"From": "+15045551111"}, research=research, budget=budget)
    _, again = _run({"From": "+15045551111"}, research=research, budget=budget)
    assert "Web: Acme Realty" in again[0]
    _, other = _run({"From": "+15045552222"}, research=research, budget=budget)
    assert len(calls) == 1
    assert "daily cap of 1 reached" in other[0]


def test_cap_zero_turns_research_off(env, monkeypatch):
    monkeypatch.setenv("MISSED_CALL_RESEARCH_DAILY_CAP", "0")

    async def research(kind, query):  # pragma: no cover - must not run
        raise AssertionError("research must not run")

    _, sent = _run({"From": "+15045551111"}, research=research)
    assert "research off" in sent[0]


def test_hidden_caller_still_texts_and_spends_nothing(env):
    async def research(kind, query):  # pragma: no cover
        raise AssertionError("no research for a hidden number")

    out, sent = _run({"From": "anonymous"}, research=research)
    assert out["researched"] is False
    assert "anonymous" in sent[0] and "lookup?" not in sent[0]


def test_forwarding_that_shows_ryans_own_number_says_so(env):
    out, sent = _run({"From": "+15045559999"})
    assert out["outcome"] == "caller id hidden by forwarding"
    assert "caller is hidden" in sent[0]


def test_sms_failure_is_logged_not_raised(env):
    async def load():
        return []

    def boom(body):
        return None  # send_sms returns None after logging a failure

    out = asyncio.run(mcs.handle_missed_call(
        {"From": "+15045551111"}, load_leads=load, research=None, send=boom,
        now=NOW, budget=mcs.ResearchBudget()))
    assert out["sms_sid"] is None


def test_budget_resets_on_a_new_day():
    b = mcs.ResearchBudget()
    assert b.claim("5045551111", "2026-11-13", 1) == "ok"
    assert b.claim("5045552222", "2026-11-13", 1).startswith("daily cap")
    assert b.claim("5045552222", "2026-11-14", 1) == "ok"


# ------------------------------------------------------------ the route
@pytest.fixture
def client(monkeypatch, env):
    monkeypatch.setenv("AIRTABLE_ENABLED", "false")
    monkeypatch.setenv("AIRTABLE_WEBHOOK_ENABLED", "false")
    monkeypatch.setenv("APP_PASSWORD", "pw")
    from services.opportunity_service import reset_opportunity_service
    reset_opportunity_service()
    from server import app
    with TestClient(app) as test_client:
        yield test_client


def _signed(params):
    return RequestValidator(TOKEN).compute_signature(URL, params)


def test_route_needs_no_password_but_a_valid_twilio_signature(client, monkeypatch):
    sent = []
    monkeypatch.setattr(mcs, "send_sms", lambda body: sent.append(body) or "SM9")

    async def no_research(kind, query):
        return {"answer": "CALLER: unknown"}

    import services.perplexity_service as pplx
    monkeypatch.setattr(pplx, "research_async", no_research)

    params = {"CallSid": "CA-route-1", "From": "+15045557777", "To": "+15045550001"}
    bad = client.post("/api/twilio/voice/missed-call", data=params,
                      headers={"X-Twilio-Signature": "nope"})
    assert bad.status_code == 403
    assert sent == []

    ok = client.post("/api/twilio/voice/missed-call", data=params,
                     headers={"X-Twilio-Signature": _signed(params)})
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("application/xml")
    assert "<Say>" in ok.text
    assert len(sent) == 1 and "(504) 555-7777" in sent[0]

    # Twilio re-sending the same call does not text twice.
    again = client.post("/api/twilio/voice/missed-call", data=params,
                        headers={"X-Twilio-Signature": _signed(params)})
    assert again.status_code == 200 and len(sent) == 1


def test_other_routes_stay_locked(client):
    assert client.get("/api/config").status_code == 401
    assert client.get("/api/twilio/voice/missed-call").status_code in (401, 405)


def test_route_refuses_when_not_configured(client, monkeypatch):
    monkeypatch.delenv("MISSED_CALL_NOTIFY_NUMBER")
    r = client.post("/api/twilio/voice/missed-call", data={"From": "+15045557777"})
    assert r.status_code == 503


def test_sms_stays_plain_ascii_and_two_segments_max(env):
    lead = dict(LEADS[0], decision_maker="Jos\u00e9 \u201cJoe\u201d D\u2019Amico \U0001F600",
                project_address="9" * 400)
    body = mcs.build_sms(caller="+15045550142", digits="5045550142", when=NOW, lead=lead)
    assert body.isascii()
    assert len(body) <= 306 and body.endswith("...")
    assert 'Jose "Joe" D\'Amico' in body
