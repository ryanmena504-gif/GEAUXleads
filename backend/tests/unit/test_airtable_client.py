"""Every Airtable client must have a timeout — a stalled read froze prod once."""
from __future__ import annotations

import pathlib
import re

from services.airtable_client import AIRTABLE_TIMEOUT, make_api


def test_make_api_sets_a_finite_timeout():
    api = make_api("patFAKE")
    assert api.timeout == AIRTABLE_TIMEOUT
    assert all(isinstance(t, (int, float)) and t > 0 for t in AIRTABLE_TIMEOUT)


def test_no_service_builds_a_bare_pyairtable_client():
    services = pathlib.Path(__file__).resolve().parents[2] / "services"
    offenders = [
        p.name for p in services.glob("*.py")
        if p.name != "airtable_client.py" and re.search(r"\bApi\(", p.read_text())
    ]
    assert offenders == []
