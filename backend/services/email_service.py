"""
Emergent-managed Resend email sender.

Owns the outbound send call and nothing else — the caller supplies subject,
recipient, and message. Never logs the API key.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

log = logging.getLogger("bloodhound.email")

# CONSTANT — never read from env so a missing platform-injected var can't break sends.
EMAIL_BASE_URL = "https://integrations.emergentagent.com"


class EmailSendError(Exception):
    """Raised when the outbound provider rejects the send. Carries the upstream
    HTTP status so the API layer can map to a graceful 4xx/5xx."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


async def send_outreach_email(
    *,
    recipient_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> Dict[str, Any]:
    """Send a single transactional email via the Emergent-managed Resend proxy.

    Returns the provider response payload (includes `id` on success).
    Raises EmailSendError on any non-2xx.
    """
    key = os.environ.get("EMERGENT_EMAIL_KEY")
    from_name = os.environ.get("EMAIL_FROM_NAME")
    if not key:
        raise EmailSendError("EMERGENT_EMAIL_KEY missing from backend env", status_code=503)
    if not from_name:
        raise EmailSendError("EMAIL_FROM_NAME missing from backend env", status_code=503)

    payload: Dict[str, Any] = {
        "to": [recipient_email],
        "subject": subject,
        "html": html_body,
        "from_name": from_name,
    }
    if text_body:
        payload["text"] = text_body
    if reply_to:
        payload["contact_email"] = reply_to

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{EMAIL_BASE_URL}/api/v1/email/send",
                headers={"X-Email-Key": key},
                json=payload,
            )
        if resp.status_code >= 400:
            body_snippet = (resp.text or "")[:400]
            log.error("Resend send failed: %d %s", resp.status_code, body_snippet)
            raise EmailSendError(
                f"Provider rejected email ({resp.status_code}): {body_snippet}",
                status_code=resp.status_code,
            )
        try:
            data = resp.json()
        except Exception:
            data = {}
        return {"id": data.get("id"), "raw": data}
    except httpx.HTTPError as e:
        log.exception("Resend network error")
        raise EmailSendError(f"Email transport error: {e}", status_code=502) from e
