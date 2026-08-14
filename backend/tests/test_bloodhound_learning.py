from services.predictive_engine import (
    CONTACT_NOW,
    NOT_A_FIT,
    WATCH,
    PredictiveEngine,
)
from services.reply_intelligence import ReplyIntelligence


def base_record(**overrides):
    record = {
        "id": "rec_1",
        "name": "Example Pool Builder",
        "source_url": "https://example.com/project",
        "recommendation_reason": "Pool builders can introduce premium deck and outdoor-surface work.",
        "next_best_action": "Call the office and ask who handles finish selections.",
        "company": "Example Pool Builder",
        "lane": "partner",
    }
    record.update(overrides)
    return record


def test_contact_now_requires_evidence_and_public_contact():
    engine = PredictiveEngine()
    engine.train([])
    recommendation = engine.predict(base_record(phone="504-555-1212"))
    assert recommendation.work_bucket == CONTACT_NOW
    assert recommendation.priority == "High"
    assert recommendation.training_size == 0
    assert recommendation.confidence == "learning"


def test_no_contact_stays_on_watch_and_names_the_gap():
    engine = PredictiveEngine()
    engine.train([])
    recommendation = engine.predict(base_record())
    assert recommendation.work_bucket == WATCH
    assert "A verified public business phone or email" in recommendation.evidence_gaps


def test_explicit_not_a_fit_never_becomes_contact_now():
    engine = PredictiveEngine()
    engine.train([])
    recommendation = engine.predict(base_record(phone="504-555-1212", outcome="Not a fit"))
    assert recommendation.work_bucket == NOT_A_FIT
    assert recommendation.priority == "Leave alone"


def test_learning_pattern_needs_confirmed_results():
    engine = PredictiveEngine()
    records = [
        base_record(id=f"rec_{idx}", source="designer referral", reply_classification="Estimate requested")
        for idx in range(4)
    ] + [
        base_record(id="rec_5", source="permit", reply_classification="Not interested")
    ]
    engine.train(records)
    recommendation = engine.predict(base_record(source="designer referral", phone="504-555-1212"))
    assert recommendation.training_size == 5
    assert recommendation.confidence == "pattern found"
    assert "designer referral" in recommendation.learning_note


def test_reply_helper_does_not_use_notes_as_a_reply():
    helper = ReplyIntelligence()
    assert helper.classify_lead_reply({"id": "rec_1", "notes": "They asked for a quote"}) is None
    reply = helper.classify_lead_reply({"id": "rec_1", "reply_summary": "Can you send an estimate?"})
    assert reply["intent"] == "estimate_request"
    assert "estimate" in reply["suggested_action"].lower()


def test_reply_helper_marks_stop_message_as_do_not_contact():
    helper = ReplyIntelligence()
    reply = helper.classify("Please stop contacting me")
    assert reply.intent == "not_interested"
    assert "do not contact again" in reply.suggested_action.lower()
