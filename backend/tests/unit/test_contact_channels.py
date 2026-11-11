"""Contact phone / Contact email are what the app reads.

The plain Phone number and Email columns are empty on the live Leads
table. These tests pin the read order: Contact columns first, the old
columns only when the Contact columns are blank. Writes stay on the
Contact columns.
"""
from __future__ import annotations

import threading

from services.airtable_service import (
    EDITABLE_FIELDS,
    KNOWN_FIELD_MAP,
    WRITE_ALIAS,
    AirtableOpportunityService,
    _apply_view,
)
from services.contact_research import build_research_updates, enrichment_skip_reason
from services.field_norm import resolved_email, resolved_phone
from services.leads_service import LEADS_FIELD_MAP, LeadsAirtableService


TODAY = "2026-11-11"


def test_resolved_contact_wins_and_legacy_is_only_a_fallback():
    both = {
        "contact_phone": "(504) 251-5302",
        "phone": "504-000-1111",
        "phone_number": "504-000-2222",
        "phone_alt": "504-000-3333",
        "contact_email": "lazaro@reverealtors.com",
        "email": "old@legacy.test",
        "email_alt": "other@legacy.test",
    }
    assert resolved_phone(both) == "(504) 251-5302"
    assert resolved_email(both) == "lazaro@reverealtors.com"

    legacy_only = {
        "contact_phone": None,
        "phone": None,
        "phone_number": "(504) 416-3737",
        "contact_email": "",
        "email": None,
        "email_alt": "randy_leblanc@icloud.com",
    }
    assert resolved_phone(legacy_only) == "(504) 416-3737"
    assert resolved_email(legacy_only) == "randy_leblanc@icloud.com"
    assert resolved_phone({}) is None
    assert resolved_email({}) is None


def _opportunity_service():
    svc = AirtableOpportunityService.__new__(AirtableOpportunityService)
    svc._field_map = dict(KNOWN_FIELD_MAP)
    return svc


def _project(fields):
    return _opportunity_service()._record_to_opportunity({
        "id": "rec1",
        "createdTime": "2026-11-09T16:11:44.000Z",
        "fields": fields,
    })


def test_opportunity_display_uses_contact_email_not_the_empty_email_column():
    opp = _project({
        "Leads Name": "8713 Cohn St, New Orleans",
        "Contact name": "Lazaro A Suarez",
        "Contact phone": "(504) 251-5302",
        "Contact email": "lazaro@reverealtors.com",
        "Phone number": None,
        "Email": None,
    })
    assert opp["email"] == "lazaro@reverealtors.com"
    assert opp["contact_email"] == "lazaro@reverealtors.com"
    assert opp["phone"] == "(504) 251-5302"
    assert opp["contact_phone"] == "(504) 251-5302"
    assert opp["reachability"] == "Direct"


def test_opportunity_falls_back_to_the_old_columns_when_contact_columns_are_blank():
    opp = _project({
        "Leads Name": "Old columns only",
        "Contact phone": None,
        "Contact email": "",
        "Phone number": "(504) 416-3737",
        "Email": "randy_leblanc@icloud.com",
    })
    assert opp["contact_phone"] is None
    assert opp["contact_email"] is None
    assert opp["phone"] == "(504) 416-3737"
    assert opp["email"] == "randy_leblanc@icloud.com"


def test_opportunity_contact_column_wins_when_both_are_filled():
    opp = _project({
        "Leads Name": "Both filled",
        "Contact email": "real@contact.test",
        "Email": "old@legacy.test",
        "Contact phone": "(504) 251-5302",
        "Phone number": "(504) 416-3737",
    })
    assert opp["email"] == "real@contact.test"
    assert opp["phone"] == "(504) 251-5302"


class _FakeTable:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return [
            {"id": rid, "createdTime": "2026-07-01T00:00:00.000Z", "fields": dict(fields)}
            for rid, fields in self.rows.items()
        ]


def _leads(rows):
    svc = LeadsAirtableService.__new__(LeadsAirtableService)
    svc._base_id = "appTEST"
    svc._table_name = "Leads"
    svc._table_id = "tblTEST"
    svc._table = _FakeTable(rows)
    svc._cache_ttl = 0.0
    svc._lock = threading.Lock()
    svc._cache = {}
    svc._duplicate_index = {"by_record": {}, "groups": {}}
    svc._last_refresh = 0.0
    svc._field_map = dict(LEADS_FIELD_MAP)
    return svc


def test_leads_email_key_is_contact_email_when_the_email_column_is_empty():
    svc = _leads({
        "rec1": {
            "Leads Name": "8713 Cohn St",
            "recommended action": "Email the agent",
            "Contact phone": "(504) 251-5302",
            "Contact email": "lazaro@reverealtors.com",
            "Phone number": None,
            "Email": None,
            "Source URL": "https://permits.nola.gov/cohn",
        }
    })
    lead = svc.get("rec1")
    assert lead["contact_email"] == "lazaro@reverealtors.com"
    assert lead["email"] == "lazaro@reverealtors.com"
    assert lead["email_alt"] is None
    assert lead["phone"] == "(504) 251-5302"
    assert svc._has_usable_contact(lead) is True


def test_leads_fall_back_to_the_old_email_column():
    svc = _leads({
        "rec1": {
            "Leads Name": "Legacy only",
            "Contact email": None,
            "Email": "old@legacy.test",
            "Contact phone": None,
            "Phone number": "(504) 416-3737",
        }
    })
    lead = svc.get("rec1")
    assert lead["email"] == "old@legacy.test"
    assert lead["contact_email"] is None
    assert lead["phone"] == "(504) 416-3737"


def test_needs_enrichment_count_sees_a_contact_email():
    contact_only = {
        "id": "rec1",
        "current_queue": "All Projects",
        "contact_email": "lazaro@reverealtors.com",
        "email": None,
        "email_alt": None,
        "phone": None,
        "phone_alt": None,
        "governed_priority_score": None,
    }
    assert _apply_view([contact_only], "needs-enrichment") == []
    empty = {**contact_only, "id": "rec2", "contact_email": None}
    assert [row["id"] for row in _apply_view([empty], "needs-enrichment")] == ["rec2"]


def _research_lead(**overrides):
    base = {
        "id": "rec1",
        "name": "Prytania bath",
        "project_address": "1200 Prytania St",
        "source": "Permit",
        "source_category": "Permit",
        "permit_number": "23-100",
        "project_type": "bathroom remodel",
        "enrichment_status": "Ready for research",
        "contact_readiness": "Needs Public Contact",
    }
    base.update(overrides)
    return base


def test_enrichment_skips_a_lead_whose_only_address_is_contact_email():
    lead = _research_lead(contact_email="office@greigehome.com", email=None, email_alt=None, phone=None)
    assert enrichment_skip_reason(lead, today=TODAY, recheck_days=14) == "already has contact"
    bare = _research_lead(contact_email=None, email=None, email_alt=None, phone=None, contact_phone=None)
    assert enrichment_skip_reason(bare, today=TODAY, recheck_days=14) is None


def test_research_writes_still_target_the_contact_columns():
    assert WRITE_ALIAS["phone"] == "Contact phone"
    assert WRITE_ALIAS["email"] == "Contact email"
    assert "Contact phone" in EDITABLE_FIELDS
    assert "Contact email" in EDITABLE_FIELDS
    assert "Phone number" not in EDITABLE_FIELDS
    assert "Email" not in EDITABLE_FIELDS

    # A published lead can show a legacy number in `phone` while Contact
    # phone is still empty. The next research result must fill Contact
    # phone, which is the `phone` write key.
    published_legacy = _research_lead(contact_phone=None, phone="(504) 111-2222")
    updates = build_research_updates(
        published_legacy,
        {"owner_name": "Marie Ashby", "phone": "504-555-1234", "email": "marie@example.net",
         "contact_source": "homeowner", "confidence": "High"},
        today=TODAY,
    )["updates"]
    assert updates["phone"] == "(504) 555-1234"
    assert updates["email"] == "marie@example.net"

    already = _research_lead(contact_phone="(504) 111-2222", phone="(504) 111-2222")
    kept = build_research_updates(
        already,
        {"phone": "504-555-1234", "email": "marie@example.net", "contact_source": "business"},
        today=TODAY,
    )["updates"]
    assert "phone" not in kept


def test_discovery_reads_contact_columns_and_landlord_owner_phone(monkeypatch):
    from services import discovery_service as ds

    class Reader:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return list(self._rows)

    monkeypatch.setattr(ds, "get_property_manager_reader", lambda: Reader([{
        "id": "recPM",
        "review_status": "Worth a look",
        "business_name": "Greige",
        "phone": "504-000-1111",
        "contact_phone": "504-231-8890",
        "email": "old@legacy.test",
        "contact_email": "office@greigehome.com",
        "created_time": "2026-09-01T00:00:00Z",
    }]))
    managers = ds.list_property_managers("all")
    assert managers[0]["phone"] == "504-231-8890"
    assert managers[0]["email"] == "office@greigehome.com"

    monkeypatch.setattr(ds, "get_landlord_reader", lambda: Reader([{
        "id": "recL",
        "owner_name": "Mark Robertson",
        "phone": "",
        "email": None,
        "owner_phone": "225-439-3180",
        "owner_email": "mrobertsonDANE@gmail.com",
        "property_address": "1 Main St",
        "outreach_status": "Not Contacted",
        "created_time": "2026-09-02T00:00:00Z",
    }]))
    landlords = ds.list_landlords("all")
    assert landlords[0]["phone"] == "225-439-3180"
    assert landlords[0]["email"] == "mrobertsonDANE@gmail.com"

    monkeypatch.setattr(ds, "get_real_estate_agent_reader", lambda: Reader([{
        "id": "recA",
        "agent_name": "Ada",
        "public_business_phone": "504-888-1861",
        "public_business_email": "ada@brokerage.test",
        "outreach_gate": "Locked",
        "created_time": "2026-09-01T00:00:00Z",
    }]))
    agents = ds.list_real_estate_agents("all")
    assert agents[0]["phone"] == "504-888-1861"
    assert agents[0]["email"] == "ada@brokerage.test"
