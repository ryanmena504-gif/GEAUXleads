from services import audit


def test_derived_key_is_stable_within_a_scope():
    a = audit.derive_idempotency_key("approve", "rec1", scope="2026-08-02")
    b = audit.derive_idempotency_key("approve", "rec1", scope="2026-08-02")
    assert a == b and a.startswith("idem_")


def test_derived_key_changes_with_action_entity_and_day():
    base = audit.derive_idempotency_key("approve", "rec1", scope="2026-08-02")
    assert base != audit.derive_idempotency_key("revert", "rec1", scope="2026-08-02")
    assert base != audit.derive_idempotency_key("approve", "rec2", scope="2026-08-02")
    assert base != audit.derive_idempotency_key("approve", "rec1", scope="2026-08-03")


def test_store_replays_the_stored_response():
    store = audit.IdempotencyStore()
    store.put("k", {"state": "approved"})
    assert store.get("k") == {"state": "approved"}


def test_invalidate_lets_a_reverted_decision_be_retaken():
    store = audit.IdempotencyStore()
    store.put("k", {"state": "approved"})
    assert store.invalidate("k") is True
    assert store.get("k") is None
    assert store.invalidate("k") is False


def test_store_evicts_least_recently_used_entries():
    store = audit.IdempotencyStore(capacity=2)
    store.put("a", {"n": 1})
    store.put("b", {"n": 2})
    store.get("a")                 # refresh a, so b is now the coldest
    store.put("c", {"n": 3})
    assert store.get("b") is None
    assert store.get("a") is not None


def test_empty_key_is_never_stored():
    store = audit.IdempotencyStore()
    store.put("", {"n": 1})
    assert store.get("") is None


def test_recorded_event_captures_the_verdict_at_decision_time():
    log = audit.AuditLog()
    log.record(action="approve", entity_id="rec1", outcome="accepted",
               actor="ryan", eligibility={"eligible": True, "score": 78},
               changes={"Approval status": "Approved"})
    event = log.recent()[0]
    assert event["action"] == "approve"
    assert event["outcome"] == "accepted"
    assert event["actor"] == "ryan"
    assert event["eligibility"]["score"] == 78
    assert event["event_id"].startswith("evt_")


def test_actor_defaults_to_the_configured_operator(monkeypatch):
    monkeypatch.setenv("BLOODHOUND_OPERATOR", "ryan@bloodhound")
    log = audit.AuditLog()
    log.record(action="skip", entity_id="rec1", outcome="accepted")
    assert log.recent()[0]["actor"] == "ryan@bloodhound"


def test_recent_filters_and_returns_newest_first():
    log = audit.AuditLog()
    log.record(action="approve", entity_id="rec1", outcome="accepted")
    log.record(action="skip", entity_id="rec2", outcome="accepted")
    log.record(action="approve", entity_id="rec2", outcome="rejected")
    assert [e["entity_id"] for e in log.recent()] == ["rec2", "rec2", "rec1"]
    assert len(log.recent(entity_id="rec2")) == 2
    assert len(log.recent(action="approve")) == 2


def test_ring_buffer_is_bounded():
    sink = audit.LoggingRingBufferSink(capacity=3)
    log = audit.AuditLog(sink=sink)
    for i in range(10):
        log.record(action="skip", entity_id=f"rec{i}", outcome="accepted")
    assert len(log.recent(limit=100)) == 3


def test_a_custom_sink_needs_no_call_site_changes():
    written = []

    class ListSink:
        def write(self, event):
            written.append(event)

    log = audit.AuditLog(sink=ListSink())
    log.record(action="approve", entity_id="rec1", outcome="accepted")
    assert len(written) == 1
    # A non-buffering sink has no queryable history, and must say so rather
    # than pretend the trail is empty.
    assert log.recent() == []
