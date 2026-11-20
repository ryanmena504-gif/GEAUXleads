"""Interior jobs stay. A missing name or phone is not a pass."""
from services.enrichment_attempts import append_attempt
from services.mail_door import (
    KEEP,
    KEEP_MAIL_DOOR,
    PASS_EXTERIOR,
    SKIP,
    disposition,
    guard_phone_text_mission,
    is_no_contact_pass,
    phone_text_block_reason,
    restore_updates,
    review_no_contact_passes,
)


def _lead(**overrides):
    base = {
        "id": "rec1",
        "name": "2100 Saint Charles Ave",
        "project_address": "2100 Saint Charles Ave Pent F, New Orleans, LA",
        "project_type": "bathroom_remodel_tub_to_shower",
        "permit_description": "Bathroom remodel; converting tub to shower.",
        "contact_company": "Edward Rafidi",
        "source": "Permit",
        "status": "Disqualified",
        "outcome": "No usable contact",
    }
    base.update(overrides)
    return base


def test_tub_to_shower_with_a_named_person_is_mail_door():
    lead = _lead()
    assert disposition(lead) == KEEP_MAIL_DOOR
    assert phone_text_block_reason(lead) == "no-phone"


def test_kitchen_and_bath_with_a_person_is_mail_door_even_if_the_owner_is_an_llc():
    lead = _lead(
        name="2218 Joliet St",
        project_address="2218 Joliet St, New Orleans, LA 70118",
        project_type="kitchen and bathroom remodel with addition",
        permit_description="New renovation with an addition.",
        owner="C&AN Investments LLC",
        contact_name="C&AN Investments LLC",
        contact_company="Sylvester Carl Johnson",
    )
    assert disposition(lead) == KEEP_MAIL_DOOR


def test_exterior_only_stays_a_pass():
    lead = _lead(
        project_type="roof replacement",
        permit_description="Tear off and replace the roof.",
        contact_name="Ada Lovelace",
        contact_company=None,
    )
    assert disposition(lead) == PASS_EXTERIOR


def test_interior_plus_exterior_is_not_exterior_only():
    lead = _lead(
        project_type="kitchen remodel and new roof",
        permit_description="Kitchen cabinets and a roof replacement.",
        contact_name="Ada Lovelace",
        contact_company=None,
    )
    assert disposition(lead) == KEEP_MAIL_DOOR


def test_llc_multifamily_with_no_person_stays_for_enrichment():
    lead = _lead(
        name="CLS Properties 12 LLC (2514 S Tonti St -Apt 2B)",
        project_address="2514 S Tonti St -Apt 2B",
        project_type="kitchen and bathroom remodel with addition",
        permit_description="Interior paint, kitchen cabinets, bathroom renovation.",
        owner="CLS Properties 12 LLC",
        contact_name="CLS Properties 12 LLC",
        contact_company=None,
        applicant="Feelgood Construction Company LLC",
    )
    assert disposition(lead) == KEEP_MAIL_DOOR


def test_interior_job_with_no_name_and_no_phone_is_kept():
    lead = _lead(contact_company=None, contact_name=None, owner=None, decision_maker=None)
    assert disposition(lead) == KEEP_MAIL_DOOR
    nameless = _lead(
        contact_company=None,
        contact_name=None,
        owner=None,
        project_address=None,
        project_type="venetian plaster shower",
    )
    assert disposition(nameless) == KEEP


def test_llc_multifamily_with_a_named_applicant_is_kept():
    lead = _lead(
        project_address="3435 Louisiana Avenue Pkwy -Apt 2B",
        project_type="multi-family gut renovation",
        permit_description="Renovation of a gutted 4-plex. Drywall, flooring, cabinets.",
        owner="TVC Funding IV LLC",
        contact_name="TVC FUNDING IV LLC",
        contact_company=None,
        applicant="Gerald Ludwig Stawski Jr., Jimmy Taylor",
    )
    assert disposition(lead) == KEEP_MAIL_DOOR


def test_a_phone_keeps_the_lead_but_does_not_tag_mail_door():
    lead = _lead(contact_phone="504-231-8890", contact_name="Edward Rafidi")
    assert disposition(lead) == KEEP


def test_permit_phone_without_consent_cannot_be_called_or_texted():
    lead = _lead(contact_phone="504-231-8890", source="Permit Issued", sms_permission="Unknown")
    assert phone_text_block_reason(lead) == "permit-or-sale-no-consent"
    assert guard_phone_text_mission("Call Today", lead) == "Research First"
    emailed = _lead(
        contact_phone="504-231-8890",
        contact_email="ada@ashbyhome.net",
        source="Property Sale Record",
        project_type="kitchen remodel",
        contact_name="Ada Lovelace",
    )
    assert guard_phone_text_mission("Send Text", emailed) == "Send Email"


def test_consent_or_a_reply_allows_the_call():
    consented = _lead(contact_phone="504-231-8890", sms_permission="Yes")
    assert phone_text_block_reason(consented) is None
    replied = _lead(contact_phone="504-231-8890", outreach_status="Replied", sms_permission="No")
    assert phone_text_block_reason(replied) is None
    assert guard_phone_text_mission("Call Today", consented) == "Call Today"


def test_address_only_mission_becomes_a_visit_not_a_call():
    assert guard_phone_text_mission("Call Today", _lead()) == "Visit Property"
    assert guard_phone_text_mission("Send Email", _lead()) == "Send Email"
    bare = {"id": "x", "source": "Website", "recommended_action": "Call the owner"}
    assert guard_phone_text_mission("Send Text", bare) == "Research First"


def test_a_website_lead_with_a_phone_can_still_be_called():
    lead = _lead(source="Website", contact_phone="504-231-8890", sms_permission=None)
    assert phone_text_block_reason(lead) is None


def test_review_restores_mail_door_and_leaves_the_passes():
    tub = _lead(id="tub")
    roof = _lead(
        id="roof",
        project_type="roof replacement",
        permit_description="Replace the roof.",
        contact_name="Ada Lovelace",
        contact_company=None,
    )
    llc = _lead(
        id="llc",
        project_address="2514 S Tonti St -Apt 2B",
        owner="CLS Properties 12 LLC",
        contact_name="CLS Properties 12 LLC",
        contact_company=None,
        applicant="Feelgood Construction Company LLC",
    )
    other = _lead(id="other", outcome="Wrong trade")
    plan = review_no_contact_passes([tub, roof, llc, other])
    assert plan["writes"] is False
    assert [row["id"] for row in plan["restore"]] == ["tub", "llc"]
    assert {row["id"] for row in plan["keep_passed"]} == {"roof"}
    assert plan["leave"] == []
    updates = plan["restore"][0]["updates"]
    assert updates["status"] == "Needs research"
    assert updates["outcome"] == ""
    assert "mail-door" in updates["notes"]
    assert is_no_contact_pass({"activity_log_raw": "2026-11-16 | disqualified | No contact, stale (pre-Oct)"})


def test_restore_does_not_invent_a_select_option_when_notes_already_tag_it():
    lead = _lead(notes="Contact channel: mail-door", status="Needs research")
    updates = restore_updates(lead, KEEP_MAIL_DOOR)
    assert "notes" not in updates
    assert "status" not in updates
    assert updates["outcome"] == ""
    assert disposition({"name": "Mystery", "source": "Website"}) == SKIP


def _failed_log(*stamps):
    text = ""
    for stamp in stamps:
        text = append_attempt(text, {
            "timestamp": stamp,
            "source": "perplexity:homeowner_lookup",
            "result": "not_found",
            "found": {},
        })
    return text


def test_one_failed_attempt_does_not_keep_a_no_contact_pass_closed():
    tub = _lead(id="tub", activity_log_raw=_failed_log("2026-11-01T15:00:00+00:00"))
    plan = review_no_contact_passes([tub])
    assert [row["id"] for row in plan["restore"]] == ["tub"]


def test_two_failed_attempts_stay_passed_and_the_address_stays_mail_door():
    tub = _lead(
        id="tub",
        activity_log_raw=_failed_log("2026-11-01T15:00:00+00:00", "2026-11-18T15:00:00+00:00"),
    )
    assert disposition(tub) == KEEP_MAIL_DOOR
    plan = review_no_contact_passes([tub])
    assert plan["restore"] == []
    assert [row["id"] for row in plan["keep_passed"]] == ["tub"]
