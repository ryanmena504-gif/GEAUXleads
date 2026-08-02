"""Approve / revert semantics, offline.

`LeadsAirtableService` is instantiated without running `__init__` so no Airtable
connection is opened. A fake table records writes in memory, which lets the
approval path be exercised end to end without touching the live base.
"""
import pytest

from services import audit
from services.audit import derive_idempotency_key
from services.leads_service import (
    EDITABLE_FIELDS,
    LEADS_FIELD_MAP,
    LeadsAirtableService,
    OutreachBlocked,
)


class FakeTable:
    """Stands in for pyairtable's Table. Records every write."""

    def __init__(self, rows):
        self.rows = rows
        self.writes = []
        self.rejected_values = set()

    def all(self):
        return [{"id": rid, "createdTime": "2026-07-01T00:00:00.000Z", "fields": dict(f)}
                for rid, f in self.rows.items()]

    def update(self, record_id, fields):
        for name, value in fields.items():
            if value in self.rejected_values:
                raise ValueError(f"{value!r} is not a configured select option")
        self.writes.append((record_id, dict(fields)))
        self.rows[record_id].update(fields)
        return {"id": record_id, "fields": self.rows[record_id]}


APPROVABLE_FIELDS = {
    "Leads Name": "Ashby Residence Roof Replacement",
    "Next action": "Call Marie about the Prytania roof permit",
    "Contact name": "Marie Ashby",
    "Contact phone": "504-231-8890",
    "Contact email": "marie.ashby@ashbyhome.net",
    "Address": "1428 Prytania St",
    "City": "New Orleans",
    "Opportunity type": "Roof Replacement",
    "contact confidence": "High",
    "Lead score": 78,
    "First message": "Hi Marie — saw the permit filing on Prytania.",
    "Status": "New",
}


def make_service(rows, audit_log=None):
    svc = LeadsAirtableService.__new__(LeadsAirtableService)
    svc._base_id = "appTEST"
    svc._table_name = "Leads"
    svc._table_id = "tblTEST"
    svc._table = FakeTable(rows)
    svc._cache_ttl = 0.0
    import threading
    svc._lock = threading.Lock()
    svc._cache = {}
    svc._duplicate_index = {"by_record": {}, "groups": {}}
    svc._last_refresh = 0.0
    svc._field_map = dict(LEADS_FIELD_MAP)
    svc._schema_field_names = sorted(LEADS_FIELD_MAP)
    svc._skipped = set()
    svc._held = set()
    svc._approvals = {}
    svc._audit = audit_log or audit.AuditLog()
    return svc


@pytest.fixture
def service():
    return make_service({"rec1": dict(APPROVABLE_FIELDS)})


# --------------------------------------------------------------- approval
def test_approve_writes_only_allowlisted_fields(service):
    result = service.approve("rec1", actor="ryan")
    assert result["state"] == "approved"
    written = {name for _, fields in service._table.writes for name in fields}
    assert written <= EDITABLE_FIELDS
    assert written == {"Approval status", "Outreach status"}


def test_approve_does_not_claim_a_message_was_sent(service):
    result = service.approve("rec1")
    assert "no message has been sent" in result["note"].lower()
    assert result["recipient"]["phone"] == "(504) 231-8890"


def test_ineligible_lead_is_refused_with_structured_reasons():
    svc = make_service({"rec1": {"Leads Name": "Skeleton row",
                                 "Next action": "Review"}})
    with pytest.raises(OutreachBlocked) as exc:
        svc.approve("rec1")
    codes = {b["code"] for b in exc.value.result.to_dict()["blockers"]}
    assert "no_verified_contact" in codes
    assert svc._table.writes == []          # nothing written on refusal


def test_refusal_is_audited_as_rejected():
    log = audit.AuditLog()
    svc = make_service({"rec1": {"Leads Name": "Skeleton", "Next action": "Review"}},
                       audit_log=log)
    with pytest.raises(OutreachBlocked):
        svc.approve("rec1", actor="ryan")
    event = log.recent()[0]
    assert event["outcome"] == "rejected"
    assert event["eligibility"]["eligible"] is False


def test_approval_is_audited_with_the_verdict_and_acknowledged_warnings():
    log = audit.AuditLog()
    fields = dict(APPROVABLE_FIELDS)
    del fields["contact confidence"]        # produces a confidence_unknown warning
    svc = make_service({"rec1": fields}, audit_log=log)
    svc.approve("rec1", actor="ryan", acknowledged_warnings=["confidence_unknown"])
    event = log.recent()[0]
    assert event["outcome"] == "accepted"
    assert event["metadata"]["acknowledged_warnings"] == ["confidence_unknown"]
    assert event["eligibility"]["eligible"] is True


def test_unknown_lead_raises_keyerror(service):
    with pytest.raises(KeyError):
        service.approve("recNOPE")


# ------------------------------------------------------------ idempotency
def test_replayed_approval_does_not_write_twice(service):
    first = service.approve("rec1", idempotency_key="k-1")
    writes_after_first = len(service._table.writes)
    second = service.approve("rec1", idempotency_key="k-1")
    assert second["replayed"] is True
    assert second["approved_at"] == first["approved_at"]
    assert len(service._table.writes) == writes_after_first


def test_replay_is_audited_without_a_second_acceptance():
    log = audit.AuditLog()
    svc = make_service({"rec1": dict(APPROVABLE_FIELDS)}, audit_log=log)
    svc.approve("rec1", idempotency_key="k-1")
    svc.approve("rec1", idempotency_key="k-1")
    outcomes = [e["outcome"] for e in log.recent(action="approve")]
    assert outcomes.count("accepted") == 1
    assert outcomes.count("replayed") == 1


def test_a_double_click_without_a_client_key_still_approves_once(service):
    service.approve("rec1")
    service.approve("rec1")
    assert len(service._table.writes) == 2      # both fields, from one approval


# ----------------------------------------------------------------- revert
def test_revert_clears_the_session_approval_and_writes_a_status(service):
    service.approve("rec1")
    result = service.revert_approval("rec1", actor="ryan", reason="wrong lead")
    assert result["state"] == "approval_reverted"
    assert result["reverted_to"] == "Pending"
    assert "rec1" not in service._approvals


def test_revert_degrades_through_the_select_vocabulary(service):
    service._table.rejected_values = {"Pending", "Pending Approval"}
    service.approve("rec1")
    assert service.revert_approval("rec1")["reverted_to"] == "Needs Review"


def test_revert_allows_a_deliberate_re_approval_on_the_same_day(service):
    """Without invalidating the idempotency entry the re-approve would be
    silently swallowed as a replay."""
    key = derive_idempotency_key("approve", "rec1")
    service.approve("rec1")
    service.revert_approval("rec1")
    assert service._audit.idempotency.get(key) is None
    again = service.approve("rec1")
    assert again.get("replayed") is not True


def test_revert_states_that_nothing_was_dispatched(service):
    service.approve("rec1")
    assert "no message had been dispatched" in service.revert_approval("rec1")["note"].lower()


# ------------------------------------------------------------ queue safety
def test_suppressed_duplicate_never_becomes_the_next_best_action():
    thin = {k: v for k, v in APPROVABLE_FIELDS.items()
            if k in ("Leads Name", "Next action", "Contact phone")}
    svc = make_service({"rec1": dict(APPROVABLE_FIELDS), "rec2": thin})
    pick = svc.pick_next_best_action()
    assert pick["id"] == "rec1"
    assert svc.get("rec2")["duplicate_of"] == "rec1"
    assert svc.queue_stats()["duplicates_suppressed"] == 1


def test_duplicate_cannot_be_approved_independently():
    thin = {k: v for k, v in APPROVABLE_FIELDS.items()
            if k in ("Leads Name", "Next action", "Contact phone")}
    svc = make_service({"rec1": dict(APPROVABLE_FIELDS), "rec2": thin})
    with pytest.raises(OutreachBlocked) as exc:
        svc.approve("rec2")
    assert "duplicate_lead" in {b["code"] for b in exc.value.result.to_dict()["blockers"]}


def test_skeleton_rows_are_excluded_from_the_queue():
    svc = make_service({"recEmpty": {"Leads Name": None, "Next action": None}})
    assert svc.pick_next_best_action() is None


def test_next_best_action_carries_the_verdict_for_the_ui(service):
    pick = service.pick_next_best_action()
    assert pick["_eligibility"]["eligible"] is True
    assert pick["_readiness"]["score_source"]
    assert "score 78" in pick["_selection_reason"]


def test_queue_stats_separate_approvable_from_merely_queued():
    unreachable = {"Leads Name": "No contact", "Next action": "Research"}
    svc = make_service({"rec1": dict(APPROVABLE_FIELDS), "rec2": unreachable})
    stats = svc.queue_stats()
    assert stats["eligible"] == 2
    assert stats["approvable"] == 1
    assert stats["blocked_by_policy"] == 1


def test_hold_and_skip_remove_a_lead_from_the_queue(service):
    service.skip("rec1")
    assert service.pick_next_best_action() is None
    service._skipped.clear()
    service.hold("rec1")
    assert service.pick_next_best_action() is None


def test_update_message_is_audited_with_the_previous_value(service):
    service.update_message("rec1", "New draft", actor="ryan")
    event = service._audit.recent(action="update_message")[0]
    assert event["changes"]["First message"]["to"] == "New draft"
    assert event["changes"]["First message"]["from"] == APPROVABLE_FIELDS["First message"]


def test_writes_outside_the_allowlist_are_refused(service):
    assert service._safe_update("rec1", "Lead score", 99) is False
    assert service._table.writes == []
