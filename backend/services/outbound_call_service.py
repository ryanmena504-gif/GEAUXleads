"""Place a call to a lead through the existing Twilio account.

Bridge (default): Twilio calls Ryan first. When he answers, it dials the
lead with the shop number as caller ID. If Ryan's side is a voicemail,
the lead is not dialed.

Message: Twilio calls the lead and plays the same voice as the missed-call
greeting. Press 1 connects them to Ryan. A machine gets a short voicemail
after the beep.
"""
from __future__ import annotations

import logging
from typing import Any, Dict
from urllib.parse import urlencode
from xml.sax.saxutils import escape

from services import outbound_contact as contact
from services.missed_call_service import say_language, say_voice

log = logging.getLogger("bloodhound.outbound.call")

_XML_ATTR = {'"': "&quot;", "'": "&apos;"}
_INTRO = (
    "Hi, this is Ryan's assistant at The Shirtless Handyman. "
    "Ryan asked me to reach out. Press 1 to be connected to him."
)
_VOICEMAIL = (
    "Hi, this is Ryan's assistant at The Shirtless Handyman. "
    "Ryan wanted to reach you and missed you. "
    "You can call the shop back at {spoken}. Thanks, and have a good day."
)
_DIGIT_WORDS = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
)


def _xml(inner: str) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><Response>' + inner + "</Response>"


def _attr(value: str) -> str:
    return escape(value, _XML_ATTR)


def _say(text: str) -> str:
    voice = _attr(say_voice())
    language = _attr(say_language())
    return f'<Say language="{language}" voice="{voice}">{escape(text)}</Say>'


def _hangup() -> str:
    return _xml("<Hangup/>")


def spoken_phone(e164: str) -> str:
    digits = (e164 or "").lstrip("+")
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) != 10 or not digits.isdigit():
        return "the shop"
    groups = (digits[0:3], digits[3:6], digits[6:])
    return ", ".join(" ".join(_DIGIT_WORDS[int(d)] for d in group) for group in groups)


def _lead_name(lead: Dict[str, Any]) -> str:
    raw = str(lead.get("decision_maker") or lead.get("name") or "").strip()
    raw = " ".join(raw.split())
    return raw[:80]


def _is_machine(answered_by: str) -> bool:
    text = (answered_by or "").strip().lower()
    return text.startswith("machine") or text == "fax"


def _callback(kind: str, lead_id: str, mode: str) -> str:
    query = urlencode({"lead_id": contact.safe_id(lead_id), "mode": mode})
    return contact.public_url(f"/api/twilio/voice/outbound/{kind}", query)


def place_call(lead: Dict[str, Any], mode: str) -> Dict[str, str]:
    """One REST call. max_retries is 0 on the client, so a failure is not repeated."""
    mode = "message" if mode == "message" else "bridge"
    shop = contact.from_number()
    owner = contact.owner_number()
    destination = owner if mode == "bridge" else contact.lead_e164(lead)
    if not shop or not destination:
        raise contact.ProviderError("Twilio did not place the call.")
    url_kind = "bridge" if mode == "bridge" else "message"
    kwargs = {
        "to": destination,
        "from_": shop,
        "url": _callback(url_kind, lead.get("id"), mode),
        "method": "POST",
        "status_callback": _callback("status", lead.get("id"), mode),
        "status_callback_method": "POST",
        "status_callback_event": ["initiated", "ringing", "answered", "completed"],
        "machine_detection": "Enable" if mode == "bridge" else "DetectMessageEnd",
    }
    if mode == "message":
        kwargs["machine_detection_timeout"] = 30
    try:
        call = contact.twilio_client().calls.create(**kwargs)
    except Exception as exc:  # noqa: BLE001
        contact.log_provider("Outbound call", exc)
        raise contact.ProviderError("Twilio did not place the call.") from exc
    sid = contact.safe_sid(getattr(call, "sid", "") or "")
    status = str(getattr(call, "status", "") or "queued")
    if not sid:
        raise contact.ProviderError("Twilio did not place the call.")
    log.info("Outbound call placed lead=%s mode=%s sid=%s", lead.get("id"), mode, sid)
    return {"sid": sid, "status": status, "mode": mode}


def bridge_twiml(lead: Dict[str, Any], answered_by: str) -> str:
    """Played to Ryan. A machine hangs up so the lead is never connected to voicemail."""
    if _is_machine(answered_by):
        return _hangup()
    number = contact.lead_e164(lead)
    shop = contact.from_number() or ""
    if not number or not shop:
        return _xml(_say("That lead has no phone number on file.") + "<Hangup/>")
    name = _lead_name(lead)
    intro = f"Connecting you to {name}." if name else "Connecting you now."
    dial = (
        f'<Dial callerId="{_attr(shop)}" timeout="25">'
        f"<Number>{escape(number)}</Number></Dial>"
    )
    return _xml(_say(intro) + dial)


def message_twiml(lead: Dict[str, Any], answered_by: str) -> str:
    shop = contact.from_number() or ""
    if _is_machine(answered_by):
        spoken = spoken_phone(shop)
        return _xml(_say(_VOICEMAIL.format(spoken=spoken)) + "<Hangup/>")
    action = _attr(_callback("gather", lead.get("id"), "message"))
    gather = (
        f'<Gather input="dtmf" numDigits="1" timeout="6" method="POST" action="{action}">'
        f"{_say(_INTRO)}</Gather>"
    )
    goodbye = (
        "No problem. You can call the shop at "
        + spoken_phone(shop)
        + ". Goodbye."
    )
    return _xml(gather + _say(goodbye) + "<Hangup/>")


def gather_twiml(lead: Dict[str, Any], digits: str) -> str:
    if (digits or "").strip() != "1":
        return _xml(_say("Goodbye.") + "<Hangup/>")
    shop = contact.from_number() or ""
    owner = contact.owner_number() or ""
    if not shop or not owner:
        return _xml(_say("Ryan isn't available right now. Please call the shop back.") + "<Hangup/>")
    whisper = _attr(_callback("whisper", lead.get("id"), "message"))
    dial = (
        f"{_say('Connecting you to Ryan.')}"
        f'<Dial callerId="{_attr(shop)}" timeout="25">'
        f'<Number url="{whisper}">{escape(owner)}</Number></Dial>'
    )
    return _xml(dial)


def whisper_twiml(lead: Dict[str, Any]) -> str:
    name = _lead_name(lead)
    line = f"{name} is on the line." if name else "A caller asked to speak with you."
    return _xml(_say(line))
