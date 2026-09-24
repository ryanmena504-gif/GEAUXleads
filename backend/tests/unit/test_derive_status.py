"""Offline tests for dashboard status derivation from manual outreach results."""
from __future__ import annotations

from services.airtable_service import _derive_status


def test_replied_outreach_becomes_conversation_started():
    assert _derive_status({"outreach_status": "Replied"}) == "Conversation started"


def test_estimate_requested_outreach_becomes_estimate_requested():
    assert _derive_status({"outreach_status": "Estimate requested"}) == "Estimate requested"


def test_not_interested_becomes_disqualified():
    assert _derive_status({"outreach_status": "Not interested"}) == "Disqualified"


def test_sent_does_not_auto_advance_status():
    # Falls through to New when nothing else is set.
    assert _derive_status({"outreach_status": "Sent"}) == "New"


def test_no_response_does_not_auto_advance_status():
    assert _derive_status({"outreach_status": "No response"}) == "New"


def test_reply_classification_not_interested_disqualifies():
    assert _derive_status({"reply_classification": "Not interested"}) == "Disqualified"


def test_flag_won_still_wins():
    assert _derive_status({"flag_won": True, "outreach_status": "Replied"}) == "Won"


def test_outreach_manual_result_beats_enrichment_research():
    assert (
        _derive_status(
            {
                "outreach_status": "Replied",
                "enrichment_status": "Needs research",
            }
        )
        == "Conversation started"
    )
