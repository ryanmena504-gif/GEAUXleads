"""Keep interior leads, log every enrichment attempt, drop only after two failures.

No network. Existing leads with no attempt lines read as an empty history
and are not dropped.
"""
from __future__ import annotations

import asyncio

from services.airtable_service import AirtableOpportunityService
from services.contact_research import (
    build_failure_updates,
    build_research_updates,
    enrichment_skip_reason,
)
from services.enrichment_attempts import (
    append_attempt,
    attempts_of,
    describe_attempt,
    parse_attempts,
    should_drop_for_no_contact,
)
from services.enrichment_batch import run_enrichment_batch
from services.mail_door import KEEP, KEEP_MAIL_DOOR, PASS_EXTERIOR, disposition
from services.opportunity_service import SampleOpportunityService


TODAY = "2026-11-11"
WHEN = "2026-11-11T15:04:00+00:00"


def _lead(**overrides):
    base = {
        "id": "rec1",
        "name": "1200 Prytania St",
        "project_address": "1200 Prytania St",
        "city": "New Orleans",
        "source": "Permit",
        "source_category": "Permit",
        "permit_number": "23-100",
        "project_type": "bathroom remodel",
        "permit_description": "Tile shower conversion.",
        "enrichment_status": "Ready for research",
        "contact_readiness": "Needs Public Contact",
    }
    base.update(overrides)
    return base


def _found(**overrides):
    base = {
        "owner_name": "Marie Ashby",
        "phone": "504-555-1234",
        "email": "marie@example.net",
        "mailing_address": "PO Box 10, New Orleans, LA 70115",
        "contact_source": "homeowner",
        "source_url": "https://assessor.example/parcel/1",
        "confidence": "High",
        "entity_context": "Assessor owner of record.",
    }
    base.update(overrides)
    return base


def _attempt(stamp, result="not_found", **found):
    return append_attempt("", {
        "timestamp": stamp,
        "source": "perplexity:homeowner_lookup",
        "result": result,
        "found": found,
    })


def test_an_existing_lead_with_no_attempt_line_is_an_empty_history():
    opp = {
        "notes": "Older research note.",
        "activity_log_raw": "2026-11-16 | disqualified | No contact, stale (pre-Oct)\nnot a log line",
        "enrichment_status": "No contact found",
    }
    assert parse_attempts(None) == []
    assert parse_attempts("garbage") == []
    assert attempts_of(opp) == []
    assert should_drop_for_no_contact(opp) is False
    history = parse_attempts(_attempt("2026-11-01T15:00:00+00:00", name="Marie Ashby"))
    assert history == [{
        "timestamp": "2026-11-01T15:00:00+00:00",
        "source": "perplexity:homeowner_lookup",
        "result": "not_found",
        "found": {"name": "Marie Ashby"},
    }]
    assert "Marie Ashby" in describe_attempt(history[0])
    assert "not found" in describe_attempt(history[0])


def test_intake_keeps_interior_work_and_skips_only_out_of_lane():
    shower = _lead(owner=None, decision_maker=None, contact_name=None, phone=None, email=None)
    assert disposition(shower) == KEEP_MAIL_DOOR
    named_with_phone = _lead(phone="(504) 555-0199", decision_maker=None, owner=None)
    assert disposition(named_with_phone) == KEEP
    no_address = _lead(project_address=None, owner=None, project_type="venetian plaster shower")
    assert disposition(no_address) == KEEP
    roof = _lead(project_type="roof replacement", permit_description="Tear off and replace the roof.")
    assert disposition(roof) == PASS_EXTERIOR
    assert disposition({"name": "Mystery", "source": "Website"}) == "skip"


def test_a_missing_name_is_not_an_enrichment_skip_and_a_phone_still_is():
    nameless = _lead(owner=None, decision_maker=None, contact_name=None)
    assert enrichment_skip_reason(nameless, today=TODAY, recheck_days=14) is None
    assert enrichment_skip_reason(
        _lead(phone="(504) 555-0199", decision_maker=None, owner=None),
        today=TODAY, recheck_days=14,
    ) == "already has contact"
    assert enrichment_skip_reason(
        _lead(project_type="roof replacement", permit_description="Replace the roof."),
        today=TODAY, recheck_days=14,
    ) == "out of lane"
    assert enrichment_skip_reason(
        _lead(enrichment_status="No contact found", contact_readiness=""),
        today=TODAY, recheck_days=14,
    ) is None


def test_two_failed_attempts_are_exhausted_and_one_is_not_a_drop():
    one = _lead(activity_log_raw=_attempt("2026-10-01T15:00:00+00:00"), contact_verified_date="2026-10-01")
    assert should_drop_for_no_contact(one) is False
    assert enrichment_skip_reason(one, today=TODAY, recheck_days=14) is None
    two = _attempt("2026-10-01T15:00:00+00:00") + "\n" + _attempt("2026-11-01T15:00:00+00:00", result="failed")
    exhausted = _lead(activity_log_raw=two, contact_verified_date=TODAY, enrichment_status="No contact found")
    assert should_drop_for_no_contact(exhausted) is True
    assert enrichment_skip_reason(exhausted, today=TODAY, recheck_days=14) == "attempts exhausted"
    reached = {**exhausted, "phone": "(504) 555-0199"}
    assert should_drop_for_no_contact(reached) is False
    assert enrichment_skip_reason(reached, today=TODAY, recheck_days=14) == "already has contact"


def test_the_first_miss_is_logged_and_the_second_miss_drops_without_deleting():
    first = build_research_updates(
        _lead(),
        _found(phone=None, email=None),
        today=TODAY,
        attempted_at=WHEN,
    )["updates"]
    assert "status" not in first
    assert "outcome" not in first
    assert first["enrichment_status"] == "No contact found"
    logged = parse_attempts(first["activity_log"])
    assert logged[0]["timestamp"] == WHEN
    assert logged[0]["source"] == "perplexity:homeowner_lookup"
    assert logged[0]["result"] == "not_found"
    assert logged[0]["found"]["name"] == "Marie Ashby"
    assert "phone" not in logged[0]["found"]

    second = build_research_updates(
        _lead(activity_log_raw=first["activity_log"], notes=first["notes"]),
        _found(phone=None, email=None, owner_name=None, mailing_address=None),
        today=TODAY,
        attempted_at="2026-11-12T15:04:00+00:00",
    )["updates"]
    assert second["status"] == "Disqualified"
    assert second["outcome"] == "No usable contact"
    assert len(parse_attempts(second["activity_log"])) == 2


def test_a_found_phone_is_logged_and_does_not_drop_the_lead():
    prior = _attempt("2026-10-01T15:00:00+00:00")
    updates = build_research_updates(
        _lead(activity_log_raw=prior),
        _found(),
        today=TODAY,
        attempted_at=WHEN,
    )["updates"]
    assert updates["phone"] == "(504) 555-1234"
    assert "status" not in updates
    history = parse_attempts(updates["activity_log"])
    assert [row["result"] for row in history] == ["not_found", "found"]
    assert history[1]["found"]["email"] == "marie@example.net"


def test_a_paid_call_failure_is_an_attempt_and_the_second_one_drops():
    first = build_failure_updates(_lead(notes="Earlier note"), "timeout", today=TODAY, attempted_at=WHEN)
    assert first["updates"]["enrichment_status"] == "Research failed"
    assert "status" not in first["updates"]
    assert parse_attempts(first["updates"]["activity_log"])[0]["result"] == "failed"
    assert "not retried" in first["updates"]["notes"].lower()
    second = build_failure_updates(
        _lead(activity_log_raw=first["updates"]["activity_log"]),
        "timeout",
        today=TODAY,
        attempted_at="2026-11-12T15:04:00+00:00",
    )
    assert second["updates"]["status"] == "Disqualified"
    assert len(parse_attempts(second["updates"]["activity_log"])) == 2


def _run(leads, research):
    writes = []

    async def update(oid, fields):
        writes.append((oid, dict(fields)))

    stats = asyncio.run(run_enrichment_batch(
        leads,
        research=research,
        update=update,
        draft=None,
        today=TODAY,
        cap=10,
        recheck_window=14,
        failure_limit=3,
    ))
    return stats, writes


def test_the_morning_batch_attempts_a_lead_with_no_contact_and_fewer_than_two_tries():
    calls = []

    async def research(opp):
        calls.append(opp["id"])
        return _found(phone=None, email=None)

    waiting = _lead(
        id="waiting",
        enrichment_status="No contact found",
        contact_readiness="",
        owner=None,
        decision_maker=None,
    )
    roof = _lead(
        id="roof",
        project_type="roof replacement",
        permit_description="Tear off and replace the roof.",
    )
    done = _lead(
        id="done",
        activity_log_raw=_attempt("2026-10-01T15:00:00+00:00") + "\n" + _attempt("2026-11-01T15:00:00+00:00"),
        enrichment_status="No contact found",
        contact_readiness="",
        contact_verified_date="2026-10-01",
    )
    stats, writes = _run([waiting, roof, done], research)
    assert calls == ["waiting"]
    assert stats["dropped_no_contact"] == 1
    assert all(fields.get("status") != "Disqualified" or oid == "done" for oid, fields in writes)
    dropped = [fields for oid, fields in writes if oid == "done"]
    assert dropped[0]["status"] == "Disqualified"
    assert dropped[0]["outcome"] == "No usable contact"
    assert not any(oid == "roof" for oid, _fields in writes)


def test_api_response_includes_attempt_history_and_the_detail_timeline_is_readable():
    sample = SampleOpportunityService()
    assert sample.get(sample.all()[0]["id"])["enrichment_attempts"] == []
    logged = sample.get("opp_002")
    assert [row["result"] for row in logged["enrichment_attempts"]] == ["not_found", "found"]
    assert logged["enrichment_attempts"][1]["found"]["name"] == "Elena Boudreaux"

    svc = AirtableOpportunityService.__new__(AirtableOpportunityService)
    svc._field_map = {
        "Activity Log": "activity_log_raw",
        "Leads Name": "name",
        "Address": "project_address",
        "Opportunity type": "project_type",
        "Permit description": "permit_description",
    }
    log = _attempt("2026-11-18T15:04:00+00:00", name="Marie Ashby")
    opp = svc._record_to_opportunity({
        "id": "recAttempt",
        "createdTime": "2026-11-01T00:00:00.000Z",
        "fields": {
            "Activity Log": log,
            "Leads Name": "1200 Prytania St",
            "Address": "1200 Prytania St",
            "Opportunity type": "bathroom remodel",
            "Permit description": "Shower conversion.",
        },
    })
    assert opp["enrichment_attempts"] == [{
        "timestamp": "2026-11-18T15:04:00+00:00",
        "source": "perplexity:homeowner_lookup",
        "result": "not_found",
        "found": {"name": "Marie Ashby"},
    }]
    notes = [item["note"] for item in opp["activity_timeline"] if item["type"] == "enrichment_attempt"]
    assert len(notes) == 1
    assert "Marie Ashby" in notes[0]
    assert "not found" in notes[0]
    assert "{" not in notes[0]
    assert disposition(opp) == KEEP_MAIL_DOOR
