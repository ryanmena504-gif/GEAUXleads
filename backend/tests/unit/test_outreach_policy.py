"""Outreach eligibility policy.

The class of bug these guard against is a record that is obviously not
contactable being reported as approvable — score 0 with no phone and no email
was the reported case.
"""
import pytest

from services import outreach_policy as policy


def codes(result):
    return {f.code for f in result.blockers}


def warning_codes(result):
    return {f.code for f in result.warnings}


# --------------------------------------------------------------- happy path
def test_complete_lead_is_eligible(approvable_lead):
    result = policy.evaluate(approvable_lead)
    assert result.eligible, codes(result)
    assert result.blockers == []


def test_eligible_lead_restates_the_recipient(approvable_lead):
    recipient = policy.evaluate(approvable_lead).recipient
    assert recipient.counterparty == "Marie Ashby"
    assert recipient.channel == "phone"
    assert recipient.phone == "(504) 231-8890"
    assert recipient.email == "marie.ashby@ashbyhome.net"
    assert recipient.category == "Roof Replacement"


# ------------------------------------------------- impossible combinations
def test_empty_record_is_never_eligible():
    result = policy.evaluate({"id": "recEMPTY"})
    assert not result.eligible
    assert {"no_verified_contact", "no_address", "no_counterparty",
            "no_category", "score_below_threshold"} <= codes(result)


def test_zero_score_with_no_contact_is_not_eligible():
    """The exact combination the user reported as slipping through."""
    result = policy.evaluate({
        "id": "recZERO",
        "name": "Unknown property",
        "lead_score": 0,
        "contact_phone": None,
        "contact_email": None,
    })
    assert not result.eligible
    assert "no_verified_contact" in codes(result)
    assert "score_below_threshold" in codes(result)
    assert result.score == 0


def test_zero_score_is_recomputed_not_trusted(approvable_lead):
    """An Airtable Lead score of 0 must not veto an otherwise complete record —
    it is the automation's default, not a judgement."""
    approvable_lead["lead_score"] = 0
    result = policy.evaluate(approvable_lead)
    assert result.score_source == "computed_from_live_fields"
    assert result.eligible, codes(result)


def test_ai_prose_cannot_satisfy_a_requirement():
    """Stale enrichment text claiming everything is fine does not make a
    contactless record contactable."""
    result = policy.evaluate({
        "id": "recPROSE",
        "name": "Uptown Kitchen Remodel",
        "ai_summary": "Verified homeowner, confirmed phone, ready for outreach.",
        "why_lead_matters": "High intent, contact confirmed.",
        "missing_information": "None — record is complete.",
    })
    assert not result.eligible
    assert "no_verified_contact" in codes(result)


def test_present_but_unusable_contact_is_reported_precisely():
    result = policy.evaluate({
        "id": "recBAD",
        "contact_phone": "555-1234",
        "contact_email": "owner@example.com",
    })
    blocker = next(f for f in result.blockers if f.code == "no_verified_contact")
    assert "not a dialable" in blocker.message
    assert "not a deliverable" in blocker.message


def test_checkbox_flags_do_not_substitute_for_a_contact_method():
    result = policy.evaluate({
        "id": "recFLAG",
        "name": "Flagged lead",
        "contact_found": True,
        "verified_opportunity": True,
        "qualified_opportunity": True,
    })
    assert "no_verified_contact" in codes(result)
    assert not result.eligible


def test_city_only_address_blocks(approvable_lead):
    approvable_lead["address"] = "New Orleans"
    result = policy.evaluate(approvable_lead)
    assert "no_address" in codes(result)
    assert "Only a city" in next(
        f.message for f in result.blockers if f.code == "no_address")


def test_missing_category_blocks(approvable_lead):
    approvable_lead["opportunity_type"] = None
    assert "no_category" in codes(policy.evaluate(approvable_lead))


def test_business_without_a_named_person_warns_but_does_not_block(approvable_lead):
    approvable_lead["contact_name"] = None
    approvable_lead["contact_company"] = "Ashby Holdings LLC"
    result = policy.evaluate(approvable_lead)
    assert result.eligible, codes(result)
    assert "org_only_counterparty" in warning_codes(result)


def test_no_counterparty_at_all_blocks(approvable_lead):
    approvable_lead["contact_name"] = None
    assert "no_counterparty" in codes(policy.evaluate(approvable_lead))


# ------------------------------------------------------------------- risk
def test_blocking_risk_flag_stops_approval(approvable_lead):
    approvable_lead["risk_flags"] = ["Homeowner opted out"]
    result = policy.evaluate(approvable_lead)
    assert "blocking_risk_flag" in codes(result)
    assert not result.eligible


def test_advisory_risk_flag_only_warns(approvable_lead):
    approvable_lead["risk_flags"] = ["price sensitive"]
    result = policy.evaluate(approvable_lead)
    assert result.eligible, codes(result)
    assert "advisory_risk_flag" in warning_codes(result)


def test_do_not_contact_status_blocks(approvable_lead):
    approvable_lead["status"] = "Do Not Contact"
    assert "marked_do_not_contact" in codes(policy.evaluate(approvable_lead))


def test_already_sent_blocks_a_second_approval(approvable_lead):
    approvable_lead["message_sent_date"] = "2026-07-30"
    assert "already_contacted" in codes(policy.evaluate(approvable_lead))


def test_suppressed_duplicate_is_not_independently_actionable(approvable_lead):
    result = policy.evaluate(approvable_lead, duplicate_of="recCANONICAL")
    assert "duplicate_lead" in codes(result)
    assert "recCANONICAL" in next(
        f.message for f in result.blockers if f.code == "duplicate_lead")


# ------------------------------------------------------------- thresholds
def test_confidence_below_threshold_blocks(approvable_lead):
    approvable_lead["contact_confidence"] = "Low"
    assert "confidence_below_threshold" in codes(policy.evaluate(approvable_lead))


def test_unrecorded_confidence_warns_rather_than_blocks(approvable_lead):
    approvable_lead["contact_confidence"] = None
    result = policy.evaluate(approvable_lead)
    assert result.eligible, codes(result)
    assert "confidence_unknown" in warning_codes(result)


def test_thresholds_are_read_from_the_environment(monkeypatch, approvable_lead):
    monkeypatch.setenv("OUTREACH_MIN_SCORE", "95")
    assert not policy.evaluate(approvable_lead,
                               thresholds=policy.PolicyThresholds.from_env()).eligible


def test_relaxing_a_requirement_records_the_check_as_unenforced(monkeypatch, approvable_lead):
    approvable_lead["address"] = None
    monkeypatch.setenv("OUTREACH_REQUIRE_ADDRESS", "false")
    result = policy.evaluate(approvable_lead,
                             thresholds=policy.PolicyThresholds.from_env())
    assert result.eligible, codes(result)
    check = next(c for c in result.checks if c["code"] == "address")
    assert "not enforced" in check["label"]


def test_malformed_threshold_env_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("OUTREACH_MIN_SCORE", "not-a-number")
    assert policy.PolicyThresholds.from_env().min_score == 50.0


# --------------------------------------------------------- both DTO shapes
def test_opportunity_dto_keys_resolve_through_the_same_policy():
    """airtable_service projects `project_address`/`project_type`/`decision_maker`
    where leads_service projects `address`/`opportunity_type`/`contact_name`."""
    result = policy.evaluate({
        "id": "opp_001",
        "name": "Garden District Restoration",
        "decision_maker": "Marie Ashby",
        "phone": "504-231-8890",
        "project_address": "1428 Prytania St",
        "project_type": "Historic Restoration",
        "contact_confidence": "High",
    })
    assert result.eligible, codes(result)
    assert result.recipient.counterparty == "Marie Ashby"


# --------------------------------------------------------------- readiness
def test_readiness_separates_live_findings_from_advisory_prose():
    report = policy.computed_readiness({
        "id": "recMIX",
        "name": "Mid-City Addition",
        "contact_phone": "504-231-8890",
        "address": "3300 Canal St",
        "opportunity_type": "Addition",
        "contact_confidence": "High",
        "missing_information": "Budget unclear, spouse not identified",
        "risk_flags": "stale",
    })
    assert report["advisory_ai_missing_information"] == [
        "Budget unclear", "spouse not identified"]
    assert report["advisory_ai_risk_flags"] == ["stale"]
    # Advisory text is namespaced, never promoted into the blocking list.
    assert all("advisory" not in m["code"] for m in report["missing_fields"])


def test_readiness_score_source_is_reported(approvable_lead):
    assert policy.computed_readiness(approvable_lead)["score_source"] == "airtable_lead_score"


def test_to_dict_is_json_shaped(approvable_lead):
    payload = policy.evaluate(approvable_lead).to_dict()
    assert set(payload) >= {"eligible", "score", "score_source", "blockers",
                            "warnings", "checks", "recipient", "thresholds"}
    assert isinstance(payload["blockers"], list)
    assert isinstance(payload["recipient"], dict)
