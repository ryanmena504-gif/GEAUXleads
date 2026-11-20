"""Send one text to a lead from the shop Twilio number.

The body always ends with 'Reply STOP to opt out' when that line is missing.
An inbound STOP (or START) is handled on /api/twilio/sms/inbound. There was
no inbound SMS webhook before this; STOP is stored on the Activity Log and
Notes, which the send guard reads.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List
from urllib.parse import urlencode

from services import outbound_contact as contact
from services.draft_safety import looks_like_ai_prompt
from services.missed_call_service import caller_digits, match_leads

log = logging.getLogger("bloodhound.outbound.sms")

EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def prepare_body(body: str) -> str:
    text = (body or "").strip()
    if not text:
        raise contact.ContactRefused("empty_body", "Write a message first.")
    trip, reason = looks_like_ai_prompt(text)
    if trip and reason in ("prompt_opener", "structural_marker"):
        raise contact.ContactRefused(
            "unsafe_body",
            "That message looks like instructions, not a text to send.",
        )
    return contact.ensure_stop_line(text)


def send_text(lead: Dict[str, Any], body: str) -> Dict[str, str]:
    text = prepare_body(body)
    shop = contact.from_number()
    destination = contact.lead_e164(lead)
    if not shop or not destination:
        raise contact.ProviderError("Twilio did not send the text.")
    query = urlencode({"lead_id": contact.safe_id(lead.get("id"))})
    try:
        message = contact.twilio_client().messages.create(
            to=destination,
            from_=shop,
            body=text,
            status_callback=contact.public_url("/api/twilio/sms/status", query),
        )
    except Exception as exc:  # noqa: BLE001
        contact.log_provider("Outbound SMS", exc)
        raise contact.ProviderError("Twilio did not send the text.") from exc
    sid = contact.safe_sid(getattr(message, "sid", "") or "")
    status = str(getattr(message, "status", "") or "queued")
    if not sid:
        raise contact.ProviderError("Twilio did not send the text.")
    log.info("Outbound SMS placed lead=%s sid=%s", lead.get("id"), sid)
    return {"sid": sid, "status": status, "body": text}


def handle_inbound(params: Dict[str, str], leads: List[Dict[str, Any]], svc: Any) -> Dict[str, Any]:
    """Mark every lead with this number when the reply is STOP or START.

    Other replies are ignored. No lead row is created.
    """
    action = contact.inbound_keyword(params.get("Body") or "")
    digits = caller_digits(params.get("From"))
    sid = contact.safe_sid(params.get("MessageSid") or "")
    matches = match_leads(digits, leads) if digits and action else []
    for lead in matches:
        lead_id = lead.get("id")
        if not lead_id:
            continue
        if action == "stop":
            contact.mark_sms_opt_out(svc, lead_id, sid)
        elif action == "start":
            contact.mark_sms_opt_in(svc, lead_id, sid)
    log.info("Inbound SMS action=%s matches=%s", action or "ignored", len(matches))
    return {"action": action or "ignored", "matched": len(matches)}
