"""Offline unit suite.

These tests never touch the network. The pre-existing `tests/*_test.py` files
are live integration tests that hit a deployed URL and mutate real Airtable
records; nothing here imports them.

Every test runs against a pinned set of policy thresholds so a change to the
operator's environment cannot silently flip an assertion.
"""
import os
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

_PINNED_ENV = {
    "OUTREACH_MIN_SCORE": "50",
    "OUTREACH_MIN_CONTACT_CONFIDENCE": "medium",
    "OUTREACH_REQUIRE_ADDRESS": "true",
    "OUTREACH_REQUIRE_CATEGORY": "true",
    "OUTREACH_REQUIRE_COUNTERPARTY": "true",
    "OUTREACH_BLOCK_ON_RISK": "true",
    "OUTREACH_BLOCK_DUPLICATES": "true",
    "OUTREACH_BLOCK_ALREADY_SENT": "true",
    # Guarantees the sample backend even if a .env is present in the checkout.
    "AIRTABLE_ENABLED": "false",
}


@pytest.fixture(autouse=True)
def pinned_policy_env(monkeypatch):
    for key, value in _PINNED_ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def approvable_lead():
    """The minimum record that satisfies every blocker."""
    return {
        "id": "recAAA000000001",
        "name": "Ashby Residence Roof Replacement",
        "contact_name": "Marie Ashby",
        "contact_phone": "504-231-8890",
        "contact_email": "marie.ashby@ashbyhome.net",
        "address": "1428 Prytania St, New Orleans",
        "city": "New Orleans",
        "opportunity_type": "Roof Replacement",
        "contact_confidence": "High",
        "lead_score": 78,
        "first_message": "Hi Marie — saw the permit filing on Prytania.",
        "status": "New",
    }
