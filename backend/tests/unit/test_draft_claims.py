"""Outreach-claim rules from the 2026-11-16 review (mirror of the JS tests)."""
from services.draft_safety import TILE_CONDITIONAL, mentions_listing_pressure, soften_draft_claims


def test_tile_promise_becomes_conditional():
    for text in (
        "Zero grout, fully waterproof, goes over existing tile, no demo day. If a buyer",
        "zero grout to scrub, fully waterproof, goes right over existing tile, no demo day. If you're",
        "fully waterproof, goes over existing tile. Open to a chat?",
    ):
        out = soften_draft_claims(text)
        assert TILE_CONDITIONAL in out
        assert "no demo day" not in out.lower()


def test_soften_is_idempotent_and_keeps_conditional_copy():
    once = soften_draft_claims("It goes over existing tile, no demo day.")
    assert soften_draft_claims(once) == once
    conditional = "often right over the existing tile once I've checked it's solid."
    assert soften_draft_claims(conditional) == conditional
    assert soften_draft_claims("") == ""
    assert soften_draft_claims(None) == ""


def test_listing_pressure_detection():
    assert mentions_listing_pressure("a 1939 home cut $50,000 since September")
    assert mentions_listing_pressure("a 1966 home sitting 126 days with $24,000 in cuts")
    assert mentions_listing_pressure("a 1920 Uptown place cut three times now")
    assert not mentions_listing_pressure("If a buyer on Cohn St wants the bath redone, I can quote it fast.")
