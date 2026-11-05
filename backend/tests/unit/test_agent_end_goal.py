"""End goal + real-lead screen: the 2026-11-05 agent update.

Guards what Ryan pinned down: the end goal is replies, then booked
in-person estimates, then won jobs (finding is only the feeder); the lead
rule is "surface to coat", never "no bathroom = reject"; and picking /
classifying agents must screen for real leads — scam patterns (overpayment,
forwarding money to a third party, printed/emailed checks, payee or bank
detail requests) are flagged, never treated as leads.
"""
import asyncio

import pytest

from services import outreach_policy as policy
from services.perplexity_service import _SYSTEMS
from services.rejection_service import REJECTION_REASONS, UnknownReason, reason_for


# ------------------------------------------------------- Perplexity prompts
def test_general_prompt_exists_and_names_the_rule():
    assert "general" in _SYSTEMS
    assert "surface to coat" in _SYSTEMS["general"]
    assert "pure plumbing" in _SYSTEMS["general"]


def test_all_prompts_carry_trade_context():
    for key, prompt in _SYSTEMS.items():
        assert "Shirtless Handyman" in prompt, key
        assert "surface to coat" in prompt, key


def test_re_agent_prompt_is_not_bathroom_only():
    prompt = _SYSTEMS["re_agent_background"]
    assert "photo-ready bathroom" not in prompt
    assert "kitchens" in prompt and "living rooms" in prompt


def test_landlord_prompt_dropped_turnover_work_framing():
    assert "turnover-work" not in _SYSTEMS["landlord_background"]


# ------------------------------------------------------- daily reviewer
def test_reviewer_prompt_carries_trade_and_screen():
    from services.daily_reviewer_service import REVIEW_PROMPT

    assert "surface to coat" in REVIEW_PROMPT
    assert "NOT a general handyman" in REVIEW_PROMPT
    assert "SCAM PATTERN" in REVIEW_PROMPT


def test_reviewer_calls_general_research_type(monkeypatch):
    import services.perplexity_service as pplx
    from services.daily_reviewer_service import _check_for_new_info

    seen = {}

    async def fake_research(research_type, query):
        seen["type"] = research_type
        return {"answer": "New permit filed for a shower remodel."}

    monkeypatch.setattr(pplx, "research_async", fake_research)
    opp = {"id": "rec1", "name": "Test", "project_address": "1 Test St"}
    assert asyncio.run(_check_for_new_info(opp)) == (
        "New permit filed for a shower remodel."
    )
    assert seen["type"] == "general"


def test_reviewer_nothing_new_returns_none(monkeypatch):
    import services.perplexity_service as pplx
    from services.daily_reviewer_service import _check_for_new_info

    async def fake_research(research_type, query):
        return {"answer": "NOTHING_NEW"}

    monkeypatch.setattr(pplx, "research_async", fake_research)
    opp = {"id": "rec1", "name": "Test", "project_address": "1 Test St"}
    assert asyncio.run(_check_for_new_info(opp)) is None


# ------------------------------------------------------- outreach writer
def test_writer_prompt_carries_end_goal_and_screen():
    from services.outreach_draft_service import MODEL, SYSTEM_PROMPT

    assert MODEL == "gpt-4o-mini"  # a model switch is a separate cost decision
    assert "surface to coat" in SYSTEM_PROMPT
    assert "NOT a general handyman" in SYSTEM_PROMPT
    assert "French Quarter Alabaster" in SYSTEM_PROMPT
    assert "never give a firm price on the phone" in SYSTEM_PROMPT
    assert "FLAG: possible scam" in SYSTEM_PROMPT


# ------------------------------------------------------- rejection reasons
def test_no_surface_reason_replaces_no_bath_scope():
    assert reason_for("no_surface")["label"] == "No surface to coat"
    with pytest.raises(UnknownReason):
        reason_for("no_bath_scope")
    assert "no_bath_scope" not in {r["key"] for r in REJECTION_REASONS}


# ------------------------------------------------------- outreach policy gate
def test_pure_roof_category_blocks(approvable_lead):
    approvable_lead["opportunity_type"] = "Roof Replacement"
    result = policy.evaluate(approvable_lead)
    assert not result.eligible
    assert "no_surface_to_coat" in {f.code for f in result.blockers}


@pytest.mark.parametrize(
    "category", ["Plumbing", "Electrical work", "HVAC repair", "Solar install"]
)
def test_pure_trade_categories_block(approvable_lead, category):
    approvable_lead["opportunity_type"] = category
    result = policy.evaluate(approvable_lead)
    assert not result.eligible
    assert "no_surface_to_coat" in {f.code for f in result.blockers}


@pytest.mark.parametrize(
    "category",
    ["Bathroom Remodel", "Shower Remodel", "Kitchen Remodel",
     "Historic Restoration", "Addition"],
)
def test_surface_categories_pass_gate(approvable_lead, category):
    approvable_lead["opportunity_type"] = category
    result = policy.evaluate(approvable_lead)
    assert "no_surface_to_coat" not in {f.code for f in result.blockers}
    assert result.eligible, {f.code for f in result.blockers}


def test_surface_gate_can_be_relaxed_by_env(monkeypatch, approvable_lead):
    approvable_lead["opportunity_type"] = "Roof Replacement"
    monkeypatch.setenv("OUTREACH_REQUIRE_SURFACE", "false")
    result = policy.evaluate(
        approvable_lead, thresholds=policy.PolicyThresholds.from_env()
    )
    assert "no_surface_to_coat" not in {f.code for f in result.blockers}
    assert result.eligible
