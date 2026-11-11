"""Contact research fills the lead, and a failed paid call is not retried.

No network. Perplexity and OpenAI are fakes. Airtable is not touched.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from services.airtable_service import EDITABLE_FIELDS, EXPLICIT_READONLY
from services.contact_finder_service import parse_result
from services.contact_research import (
    annotate_contact_flags,
    build_failure_updates,
    build_name_updates,
    build_research_updates,
    enrichment_skip_reason,
    is_residential_permit,
    parse_decision_maker_name,
)
from services.enrichment_batch import run_enrichment_batch
from services.perplexity_service import _SYSTEMS


TODAY = "2026-11-11"


def _lead(**overrides):
    base = {
        "id": "rec1",
        "name": "Prytania bath",
        "project_address": "1200 Prytania St",
        "city": "New Orleans",
        "source": "Permit",
        "source_category": "Permit",
        "permit_number": "23-100",
        "project_type": "bathroom remodel",
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


def test_parse_result_reads_the_extended_json_and_ignores_fences():
    answer = """```json
    {"owner_name": "Marie Ashby", "phone": "504-555-1234", "email": "none found",
     "mailing_address": "1 Main", "contact_source": "Homeowner",
     "source_url": "https://assessor.example/1", "confidence": "high",
     "entity_context": "Matched the parcel."}
    ```"""
    parsed = parse_result(answer)
    assert parsed["owner_name"] == "Marie Ashby"
    assert parsed["email"] is None
    assert parsed["contact_source"] == "homeowner"
    assert parsed["confidence"] == "High"
    assert parsed["mailing_address"] == "1 Main"


def test_residential_permit_is_a_house_not_a_business():
    assert is_residential_permit(_lead())
    assert not is_residential_permit(_lead(project_type="commercial renovation"))
    assert not is_residential_permit(_lead(source="Website", source_category="Social", permit_number=None))
    assert not is_residential_permit(_lead(lane="partner"))


def test_found_contact_writes_the_name_to_contact_and_owner():
    built = build_research_updates(_lead(), _found(), today=TODAY)
    updates = built["updates"]
    assert updates["decision_maker"] == "Marie Ashby"
    assert updates["owner"] == "Marie Ashby"
    assert updates["owner_mailing_address"].startswith("PO Box 10")
    assert updates["phone"] == "(504) 555-1234"
    assert updates["email"] == "marie@example.net"
    assert updates["enrichment_status"] == "Contact found"
    assert updates["contact_readiness"] == "Contact Ready"
    assert updates["contact_confidence"] == "High"
    assert updates["contact_verified_date"] == TODAY
    assert updates["source_url"] == "https://assessor.example/parcel/1"
    assert updates["public_contact_evidence"].startswith("Contact source: homeowner")
    assert built["became_contact_ready"] is True


def test_existing_phone_and_permit_url_are_not_replaced():
    opp = _lead(phone="(504) 111-2222", source_url="https://permits.example/23-100", owner="Kept Owner")
    built = build_research_updates(opp, _found(), today=TODAY, force=False)
    updates = built["updates"]
    assert "phone" not in updates
    assert "source_url" not in updates
    assert "owner" not in updates
    assert updates["decision_maker"] == "Marie Ashby"


def test_manual_rerun_can_replace_the_name():
    opp = _lead(decision_maker="Old Name", owner="Old Owner")
    updates = build_research_updates(opp, _found(), today=TODAY, force=True)["updates"]
    assert updates["decision_maker"] == "Marie Ashby"
    assert updates["owner"] == "Marie Ashby"


def test_nothing_found_still_saves_the_name_and_does_not_mark_ready():
    built = build_research_updates(
        _lead(),
        _found(phone="none found", email=None, confidence="Low"),
        today=TODAY,
    )
    updates = built["updates"]
    assert updates["decision_maker"] == "Marie Ashby"
    assert "phone" not in updates
    assert updates["enrichment_status"] == "No contact found"
    assert updates["contact_readiness"] == "Needs Public Contact"
    assert built["became_contact_ready"] is False


def test_scam_pattern_is_not_a_contact_ready_lead():
    built = build_research_updates(
        _lead(),
        _found(entity_context="SCAM PATTERN: overpayment and a wire."),
        today=TODAY,
    )
    assert built["became_contact_ready"] is False
    assert "phone" not in built["updates"]
    assert built["updates"]["contact_readiness"] == "Needs Proof"


def test_failure_marks_research_failed_and_does_not_say_to_retry_automatically():
    built = build_failure_updates(_lead(notes="Earlier note"), "Could not reach Perplexity", today=TODAY)
    updates = built["updates"]
    assert updates["enrichment_status"] == "Research failed"
    assert updates["contact_verified_date"] == TODAY
    assert "contact_readiness" not in updates
    assert "Earlier note" in updates["notes"]
    assert "not retried" in updates["notes"].lower()
    assert built["became_contact_ready"] is False


def test_skip_rules_cover_recent_checks_and_the_two_queues():
    assert enrichment_skip_reason(_lead(), today=TODAY, recheck_days=14) is None
    assert enrichment_skip_reason(
        _lead(contact_readiness="Paused", enrichment_status="Needs research"),
        today=TODAY, recheck_days=14,
    ) == "not eligible"
    assert enrichment_skip_reason(
        _lead(enrichment_status="Needs research", contact_readiness="Needs Public Contact"),
        today=TODAY, recheck_days=14,
    ) is None
    assert enrichment_skip_reason(_lead(phone="(504) 555-1234"), today=TODAY, recheck_days=14) == "already has contact"
    recent = enrichment_skip_reason(
        _lead(contact_verified_date="2026-11-10"), today=TODAY, recheck_days=14,
    )
    assert recent == "checked recently"
    assert enrichment_skip_reason(
        _lead(contact_verified_date="2026-11-10"), today=TODAY, recheck_days=14, force=True,
    ) is None


def test_who_runs_this_name_parses_and_saves_onto_the_lead():
    answer = "Marie Ashby owns the property.\nDECISION_MAKER: Marie Ashby"
    assert parse_decision_maker_name(answer) == "Marie Ashby"
    assert parse_decision_maker_name("DECISION_MAKER: unknown") is None
    updates = build_name_updates(_lead(), answer)
    assert updates["decision_maker"] == "Marie Ashby"
    assert updates["owner"] == "Marie Ashby"
    assert "phone" not in updates
    # A name already on the lead is left alone unless Ryan refetches.
    kept = build_name_updates(_lead(decision_maker="Already There"), answer, force=False)
    assert "decision_maker" not in kept


def test_homeowner_phone_requires_a_do_not_call_check_and_a_business_number_does_not():
    home = annotate_contact_flags({
        "id": "recH",
        "phone": "(504) 555-1234",
        "public_contact_evidence": "Contact source: homeowner\nAssessor record.",
    })
    assert home["contact_source"] == "homeowner"
    assert home["dnc_check_required"] is True
    biz = annotate_contact_flags({
        "id": "recB",
        "phone": "(504) 555-1234",
        "notes": "Contact source: business",
    })
    assert biz["dnc_check_required"] is False
    assert annotate_contact_flags({"id": "recX"})["dnc_check_required"] is False


def test_prompts_ask_for_a_saveable_name_and_a_homeowner_record():
    assert "DECISION_MAKER:" in _SYSTEMS["decision_maker"]
    assert "homeowner_lookup" in _SYSTEMS
    assert "mailing" in _SYSTEMS["homeowner_lookup"].lower()
    assert "NAME:" in _SYSTEMS["owner_contact"]


def test_research_fields_are_writable_and_not_frozen():
    for name in (
        "Contact name",
        "Owner Mailing Address",
        "contact confidence",
        "Enrichment status",
        "Contact Readiness",
        "Contact Verified Date",
        "Public Contact Evidence",
        "First message",
        "Source URL",
    ):
        assert name in EDITABLE_FIELDS, name
        assert name not in EXPLICIT_READONLY, name


def _run(leads, research, draft=None, **kwargs):
    writes = []

    async def update(oid, fields):
        writes.append((oid, dict(fields)))

    stats = asyncio.run(run_enrichment_batch(
        leads,
        research=research,
        update=update,
        draft=draft,
        today=TODAY,
        cap=kwargs.get("cap", 10),
        recheck_window=kwargs.get("recheck_window", 14),
        failure_limit=kwargs.get("failure_limit", 3),
        dry_run=kwargs.get("dry_run", False),
        seen=kwargs.get("seen"),
    ))
    return stats, writes


def test_batch_stops_after_three_consecutive_failures_and_does_not_retry():
    calls = {"n": 0}

    async def research(opp):
        calls["n"] += 1
        raise RuntimeError("connection error")

    leads = [_lead(id=f"rec{i}", name=f"Lead {i}") for i in range(5)]
    stats, writes = _run(leads, research)
    assert calls["n"] == 3
    assert stats["stopped_early"] is True
    assert stats["failed"] == 3
    assert stats["processed"] == 3
    failed_status = [fields for _oid, fields in writes if fields.get("enrichment_status") == "Research failed"]
    assert len(failed_status) == 3


def test_batch_respects_the_daily_cap_and_a_lead_checked_today():
    calls = []

    async def research(opp):
        calls.append(opp["id"])
        return _found(owner_name=opp["name"])

    leads = [
        _lead(id="done", contact_verified_date=TODAY),
        _lead(id="next", days_on_table=40),
        _lead(id="later", days_on_table=1),
    ]
    stats, _writes = _run(leads, research, cap=2)
    assert stats["already_checked_today"] == 1
    assert calls == ["next"]
    assert stats["contact_found"] == 1


def test_the_same_lead_is_not_researched_twice_in_one_run():
    calls = []

    async def research(opp):
        calls.append(opp["id"])
        return _found()

    stats, _writes = _run([_lead(), _lead()], research)
    assert calls == ["rec1"]
    assert stats["processed"] == 1


def test_dry_run_spends_nothing():
    async def research(opp):
        raise AssertionError("dry run must not call research")

    stats, writes = _run([_lead(), _lead(id="rec2")], research, dry_run=True)
    assert writes == []
    assert stats["candidates"] == 2
    assert {row["id"] for row in stats["results"]} == {"rec1", "rec2"}


def test_a_new_contact_ready_lead_gets_one_draft_and_an_existing_draft_does_not():
    drafts = []

    async def research(opp):
        return _found()

    async def draft(opp):
        drafts.append(opp["id"])
        return {"draft": "Saw the bath permit — worth a look this week?", "subject": "Prytania", "recipe_text": "{}"}

    stats, writes = _run([_lead(), _lead(id="rec2", draft_outreach_body="Already drafted")], research, draft=draft)
    assert drafts == ["rec1"]
    assert stats["drafts"] == 1
    bodies = [fields.get("first_message") for _oid, fields in writes if fields.get("first_message")]
    assert bodies == ["Saw the bath permit — worth a look this week?"]


def test_three_draft_failures_stop_the_batch_without_another_research_call():
    calls = {"research": 0, "draft": 0}

    async def research(opp):
        calls["research"] += 1
        return _found()

    async def draft(opp):
        calls["draft"] += 1
        raise RuntimeError("openai down")

    leads = [_lead(id=f"rec{i}") for i in range(5)]
    stats, _writes = _run(leads, research, draft=draft)
    assert calls["research"] == 3
    assert calls["draft"] == 3
    assert stats["stopped_early"] is True
    assert stats["draft_failures"] == 3


def test_a_missing_openai_key_does_not_burn_the_rest_of_the_research_cap():
    calls = {"research": 0}

    async def research(opp):
        calls["research"] += 1
        return _found()

    async def draft(opp):
        raise RuntimeError("OPENAI_API_KEY is not configured")

    stats, _writes = _run([_lead(id="a"), _lead(id="b")], research, draft=draft)
    assert calls["research"] == 2
    assert stats["drafts_unconfigured"] is True
    assert stats["stopped_early"] is False
    assert stats["contact_found"] == 2


def test_daily_review_accepts_a_sync_list_and_stops_after_three_failures(monkeypatch):
    import services.perplexity_service as pplx
    from services.daily_reviewer_service import run_daily_review

    calls = {"n": 0}

    async def boom(research_type, query):
        calls["n"] += 1
        raise RuntimeError("timeout")

    monkeypatch.setattr(pplx, "research_async", boom)

    class Svc:
        def list(self):
            return [
                {"id": f"r{i}", "name": "N", "project_address": "1 St Charles"}
                for i in range(6)
            ]

        def update_fields(self, opp_id, fields):
            raise AssertionError("a failed review must not flag the lead")

    stats = asyncio.run(run_daily_review(Svc(), max_scan=6))
    assert calls["n"] == 3
    assert stats["stopped_early"] is True
    assert stats["flagged"] == 0


def test_perplexity_client_is_built_with_no_retries(monkeypatch):
    import services.perplexity_service as pplx

    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(pplx, "Perplexity", FakeClient)
    monkeypatch.setattr(pplx, "_SDK_AVAILABLE", True)
    pplx.PerplexityResearchService(api_key="pplx-test")
    assert captured["max_retries"] == 0


def test_openai_client_is_built_with_no_retries(monkeypatch):
    import openai

    captured = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Quick question about the bath?"))]
            )

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(openai, "AsyncOpenAI", FakeClient)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from services.outreach_draft_service import generate_draft

    result = asyncio.run(generate_draft({"name": "Ada", "project_address": "1 St Charles Ave"}))
    assert captured["max_retries"] == 0
    assert "Quick question" in result["draft"]


def test_manual_find_contact_refuses_a_blank_lead_without_a_paid_call():
    from services.enrichment_batch import enrich_and_persist

    class Svc:
        def update_fields(self, opp_id, fields):
            raise AssertionError("blank lead must not be written")

    async def research(opp):
        raise AssertionError("blank lead must not spend a credit")

    result = asyncio.run(enrich_and_persist(
        Svc(), {"id": "recx"}, force=True, research=research,
    ))
    assert result["outcome"] == "skipped"
    assert result["reason"] == "nothing to research"


def test_homeowner_lookup_is_the_call_for_a_residential_permit(monkeypatch):
    import services.perplexity_service as pplx
    from services.contact_finder_service import run_contact_finder

    seen = {}

    async def fake(research_type, query):
        seen["type"] = research_type
        seen["query"] = query
        return {
            "answer": (
                '{"owner_name":"Ada Lovelace","phone":"504-555-1234","email":"none found",'
                '"mailing_address":"9 Audubon","contact_source":"homeowner",'
                '"source_url":"none found","confidence":"Medium",'
                '"entity_context":"Assessor owner."}'
            ),
            "sources": [{"url": "https://assessor.example/ada", "title": "Assessor"}],
        }

    monkeypatch.setattr(pplx, "research_async", fake)
    parsed = asyncio.run(run_contact_finder(_lead()))
    assert seen["type"] == "homeowner_lookup"
    assert "1200 Prytania" in seen["query"]
    assert parsed["owner_name"] == "Ada Lovelace"
    assert parsed["source_url"] == "https://assessor.example/ada"
    assert parsed["contact_source"] == "homeowner"


def test_business_lead_stays_on_the_business_finder(monkeypatch):
    import services.perplexity_service as pplx
    from services.contact_finder_service import run_contact_finder

    seen = {}

    async def fake(research_type, query):
        seen["type"] = research_type
        return {"answer": '{"owner_name":"Pat Lee","phone":"none found","email":"none found","entity_context":"LLC."}', "sources": []}

    monkeypatch.setattr(pplx, "research_async", fake)
    parsed = asyncio.run(run_contact_finder(_lead(
        project_type="commercial renovation",
        company="Lee Builds LLC",
    )))
    assert seen["type"] == "contact_finder"
    assert parsed["contact_source"] == "business"
