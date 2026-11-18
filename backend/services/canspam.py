"""CAN-SPAM lines for a cold email.

Every commercial email needs a way to opt out and a physical postal
address. The address comes from BUSINESS_MAILING_ADDRESS. When that
variable is unset, the draft shows a placeholder. A street address is
never written into the code.
"""
from __future__ import annotations

import os

ADDRESS_ENV = "BUSINESS_MAILING_ADDRESS"
ADDRESS_PLACEHOLDER = "[physical address — set BUSINESS_MAILING_ADDRESS]"
_MARKER = 'reply "unsubscribe"'


def business_mailing_address() -> str:
    raw = (os.environ.get(ADDRESS_ENV) or "").strip()
    return raw or ADDRESS_PLACEHOLDER


def can_spam_footer() -> str:
    return "\n".join([
        "The Shirtless Handyman",
        business_mailing_address(),
        "",
        'If you\'d rather not get these emails, reply "unsubscribe" and I\'ll take you off the list.',
    ])


def ensure_canspam(body: str) -> str:
    """Append the footer once. A body that already has the opt-out line is left alone."""
    base = (body or "").strip()
    if _MARKER in base.lower():
        return base
    footer = can_spam_footer()
    return f"{base}\n\n{footer}" if base else footer
