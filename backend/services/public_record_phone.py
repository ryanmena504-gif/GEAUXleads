"""Hook for a later free public-record phone lookup.

Parish assessor rolls and the Louisiana Secretary of State publish an
owner name and a mailing address. They do not publish a phone number
this app can read today. This function is the place to add that lookup
later. It returns None on purpose.

Do not point it at Perplexity, OpenAI, Twilio, or any other paid vendor.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def lookup_public_record_phone(lead: Dict[str, Any]) -> Optional[str]:
    """Return a phone from a free public record, or None.

    TODO: read a free assessor or Secretary of State source when one
    actually publishes a phone. Until then this is a no-op.
    """
    del lead  # unused until a free source is wired
    return None
