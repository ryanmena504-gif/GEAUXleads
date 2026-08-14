"""
Retired 2026-08-14 per Rule 5: "No direct email/SMS sending exists;
only existing device-draft handoffs remain."

The Resend-based outbound send path has been fully removed from Bloodhound.
Outreach happens exclusively via device-native drafts (mailto:/sms:) that
Ryan reviews and sends himself. This shim exists only so any legacy import
fails loud instead of silent.
"""


class EmailSendError(Exception):
    """Kept only so historical stack traces from legacy tests remain readable.
    New code must not import this — the send path no longer exists."""


async def send_outreach_email(*_args, **_kwargs):  # pragma: no cover
    raise EmailSendError(
        "Direct email sending has been removed. Use the device-native "
        "mailto: draft handoff on the opportunity detail page."
    )
