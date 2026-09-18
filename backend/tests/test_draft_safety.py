"""Regression tests for the draft-safety guard.

Every case here represents either (a) a pattern that once made it to
Ryan's send screen and must never do so again, or (b) legitimate outreach
copy that must not be blocked. Keep in sync with the JS mirror in
`frontend/src/lib/draftSafety.js`.
"""
import pytest
from services.draft_safety import looks_like_ai_prompt as g


@pytest.mark.parametrize("text", [
    "You are a lead-research assistant helping a New Orleans contractor",
    "You are an AI assistant. Help me draft a warm follow-up.",
    "Please enrich this Bloodhound lead — it has been on the table",
    "Please pull decision maker + verified public business contact",
    "Please research this contractor's recent projects",
    "System: draft a warm outreach email",
    "Assistant: here's the message",
    "### Instructions\nWrite a follow-up to this permit",
    "[SYSTEM] draft a follow-up",
    "I am an AI assistant that helps contractors",
    "As an AI language model, I cannot",
])
def test_trip_prompt_shaped(text):
    trip, reason = g(text)
    assert trip, f"expected trip for {text!r}"
    assert reason in {"prompt_opener", "structural_marker"}


@pytest.mark.parametrize("text", [
    "Hi {{first_name}}, I noticed your project",
    "Hello [FILL IN NAME], following up",
    "TODO: write the follow-up email",
    "TODO: generate a subject line for this record",
    "<<PLACEHOLDER>> - fill me in",
    "Contact info: TODO: replace",
])
def test_trip_structural_markers(text):
    trip, reason = g(text)
    assert trip, f"expected trip for {text!r}"
    assert reason == "structural_marker"


@pytest.mark.parametrize("text", [None, "", "   ", "ab", "  a  "])
def test_trip_empty_or_too_short(text):
    trip, reason = g(text)
    assert trip
    assert reason in {"empty", "too_short"}


@pytest.mark.parametrize("text", [
    "Hi Ryan, I noticed your kitchen remodel permit and wanted to reach out about a specialty finish package.",
    "Just checking in to see if now is a better time to chat.",
    "Hey — following up on the pool project we spoke about last week.",
    # False-positive traps: normal copy that superficially resembles a
    # prompt marker but isn't. These MUST remain sendable.
    "Please let me know if you have any questions about the estimate.",
    "You are correct — the address is 123 Main Street.",
    "Please feel free to reach out anytime.",
    "You're welcome to swing by the job site.",
])
def test_pass_legitimate_outreach(text):
    trip, reason = g(text)
    assert not trip, f"legitimate copy incorrectly blocked: {text!r} (reason={reason})"
    assert reason is None
