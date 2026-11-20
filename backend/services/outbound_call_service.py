"""Outbound calls to a lead through the existing Twilio account.

Two modes, both placed only when Ryan taps Call (or a caller of the
password-protected route asks for one). Nothing here runs on a schedule.

bridge (default)
    Twilio rings Ryan first (OWNER_PHONE, else LEAD_NOTIFICATION_PHONE,
    else the missed-call notify number). When he answers, Twilio dials
    the lead. The lead sees the business number.

message
    Twilio rings the lead from the business number and plays a short
    message in the same voice as the missed-call greeting. Press 1
    connects them to Ryan. An answering machine gets that message as
    voicemail and no keypress prompt.

Permit and other public-record leads can be bridged. The automated
message is refused unless a consent flag is already on the lead.
Either mode is refused when the lead is opted out or the local time
is outside Monday–Saturday 9am–6pm.

Every attempt is one line on the lead's Activity Log:
    ISO time | call | mode=bridge sid=CA… status=queued
The status callback appends another line with the Twilio status and,
when Twilio sends it, the duration in seconds. Credential values are
never written into that line or into the log.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlencode
from xml.sax.saxutils import escape

from services.call_hours import hours_message, within_calling_hours
from services.field_norm import format_phone, is_valid_phone, phone_digits
from services.mail_door import has_phone_consent
from services.missed_call_service import say_language, say_voice
from services.outreach_policy import do_not_contact_message

log = logging.getLogger("bloodhound.outbound_call")
# The Twilio helper logs HTTP headers at INFO. Keep that off so a request
# line cannot land an auth header in the API log.
logging.getLogger("twilio.http_client").setLevel(logging.WARNING)

CALL_LOG_TYPE = "call"
MODES = ("bridge", "message")
_SID_RE = re.compile(r"^CA[0-9a-f]{32}$", re.I)
_STATUS_RE = re.compile(r"^[a-z][a-z-]{1,31}$")
_LEAD_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_XML_ATTR = {'"': "&quot;", "'": "&apos;"}
_PUBLIC_RECORD_RE = re.compile(
    r"permit|public[\s_-]*record|assessor|tax[\s_-]*roll|sale",
    re.I,
)
_OPT_OUT_RE = re.compile(
    r"do not contact|do not call|opted out|opt out|\bdnc\b|unsubscribed",
    re.I,
)
_OPT_OUT_FIELDS = (
    "status", "status_raw", "approval_status", "outreach_status",
    "hunt_status", "risk_flags", "do_not_call", "dnc", "opt_out",
    "opted_out", "sms_opt_out", "call_opt_out",
)
_FLAG_FIELDS = (
    "do_not_call", "dnc", "opt_out", "opted_out", "sms_opt_out",
    "call_opt_out", "suppressed", "on_suppression_list",
)
_MACHINE_ANSWERS = {
    "machine_start", "machine_end_beep", "machine_end_silence",
    "machine_end_other", "machine", "fax",
}

HUMAN_MESSAGE = (
    "Hi, this is Ryan's assistant at The Shirtless Handyman. "
    "Ryan asked me to give you a quick call. Press 1 to be connected to him."
)
VOICEMAIL_TEMPLATE = (
    "Hi, this is Ryan's assistant at The Shirtless Handyman. "
    "Sorry we missed you. You can reach Ryan at {number}. Thanks, and have a good one."
)
_CONNECTING = "Connecting you to {name}."
_NO_ANSWER = "They didn't answer. Goodbye."
_GOODBYE = "Okay. I'll let Ryan know. Goodbye."
_PRESSED = "Connecting you to Ryan."


class CallBlocked(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class CallFailed(Exception):
    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def from_number() -> str:
    return _env("TWILIO_FROM_NUMBER") or _env("MISSED_CALL_FROM_NUMBER")


def owner_number() -> str:
    return (
        _env("OWNER_PHONE")
        or _env("LEAD_NOTIFICATION_PHONE")
        or _env("MISSED_CALL_NOTIFY_NUMBER")
    )


def public_base() -> str:
    return _env("PUBLIC_BACKEND_URL").rstrip("/")


def missing_settings() -> list:
    """Env names that still have to be set. Never includes a value."""
    missing = []
    if not _env("TWILIO_ACCOUNT_SID"):
        missing.append("TWILIO_ACCOUNT_SID")
    if not _env("TWILIO_AUTH_TOKEN"):
        missing.append("TWILIO_AUTH_TOKEN")
    if not from_number():
        missing.append("TWILIO_FROM_NUMBER")
    elif not is_valid_phone(from_number()):
        missing.append("TWILIO_FROM_NUMBER (not a usable US number)")
    if not owner_number():
        missing.append("OWNER_PHONE")
    elif not is_valid_phone(owner_number()):
        missing.append("OWNER_PHONE (not a usable US number)")
    if not public_base():
        missing.append("PUBLIC_BACKEND_URL")
    return missing


def _e164(value: Any) -> Optional[str]:
    if not is_valid_phone(value):
        return None
    return "+1" + (phone_digits(value) or "")


def _same_line(left: Any, right: Any) -> bool:
    a, b = phone_digits(left), phone_digits(right)
    return bool(a and b and a == b)


def _flatten(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(_flatten(item) for item in value)
    return str(value)


def opt_out_reason(record: Dict[str, Any]) -> Optional[str]:
    """Why this lead cannot be called, or None when no opt-out flag is set.

    The homeowner Do Not Call reminder is not an opt-out. It asks Ryan
    to check the registry. It does not by itself refuse the call.
    """
    if not record:
        return None
    banned = do_not_contact_message(record)
    if banned:
        return "This lead is marked Do Not Contact. No call was placed."
    blob = " ".join(_flatten(record.get(key)) for key in _OPT_OUT_FIELDS)
    blob = blob.replace("_", " ").replace("-", " ")
    if _OPT_OUT_RE.search(blob):
        return "This lead is marked Do Not Contact. No call was placed."
    for key in _FLAG_FIELDS:
        flag = record.get(key)
        if flag is True or str(flag or "").strip().lower() in {"yes", "true", "1", "y", "on"}:
            if key in ("suppressed", "on_suppression_list"):
                return "This lead is on the suppression list. No call was placed."
            return "This lead is marked Do Not Contact. No call was placed."
    return None


def is_public_record_source(record: Dict[str, Any]) -> bool:
    blob = " ".join(
        _flatten(record.get(key))
        for key in ("source", "source_category")
    )
    return bool(_PUBLIC_RECORD_RE.search(blob))


def message_blocked_reason(record: Dict[str, Any]) -> Optional[str]:
    """Automated message mode needs consent on a permit or public-record lead."""
    if is_public_record_source(record) and not has_phone_consent(record):
        return (
            "Automated message calls need a consent flag on permit or "
            "public-record leads. No call was placed."
        )
    return None


def normalize_mode(mode: Optional[str]) -> str:
    text = (mode or "bridge").strip().lower()
    if text not in MODES:
        raise CallBlocked(422, "Mode must be bridge or message.")
    return text


def lead_e164(record: Dict[str, Any]) -> Optional[str]:
    from services.field_norm import resolved_phone
    return _e164(resolved_phone(record))


def guard_call(record: Dict[str, Any], mode: str, when: datetime) -> str:
    """Return the lead's E.164 number, or raise CallBlocked. No Twilio call yet."""
    mode = normalize_mode(mode)
    phone = lead_e164(record)
    if not phone:
        raise CallBlocked(422, "This lead has no usable phone number.")
    if _same_line(phone, owner_number()) or _same_line(phone, from_number()):
        raise CallBlocked(422, "That number is the business line. No call was placed.")
    opted_out = opt_out_reason(record)
    if opted_out:
        raise CallBlocked(409, opted_out)
    if mode == "message":
        blocked = message_blocked_reason(record)
        if blocked:
            raise CallBlocked(409, blocked)
    if not within_calling_hours(when, phone):
        raise CallBlocked(409, hours_message(phone))
    return phone


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_twilio_error(exc: BaseException) -> str:
    status = getattr(exc, "status", None)
    code = getattr(exc, "code", None)
    return f"{type(exc).__name__} status={status} code={code}"


def _client():
    from twilio.http.http_client import TwilioHttpClient
    from twilio.rest import Client

    return Client(
        _env("TWILIO_ACCOUNT_SID"),
        _env("TWILIO_AUTH_TOKEN"),
        http_client=TwilioHttpClient(timeout=15, max_retries=0),
    )


def _speakable_name(record: Dict[str, Any]) -> str:
    raw = record.get("decision_maker") or record.get("contact_name") or record.get("name") or "this lead"
    text = re.sub(r"[^A-Za-z0-9 .,'-]", "", str(raw))
    text = re.sub(r"\s+", " ", text).strip()[:40]
    return text or "this lead"


def call_note(mode: str, sid: str, status: str, duration: Optional[str] = None) -> str:
    parts = [f"mode={mode}", f"sid={sid}", f"status={status}"]
    if duration is not None:
        parts.append(f"duration={duration}")
    return " ".join(parts)


def _log_text(record: Dict[str, Any]) -> str:
    chunks = [
        record.get("activity_log_raw"),
        record.get("activity_log"),
    ]
    timeline = record.get("activity_timeline") or []
    if isinstance(timeline, list):
        chunks.extend(item.get("note") for item in timeline if isinstance(item, dict))
    return "\n".join(str(chunk or "") for chunk in chunks)


def _already_logged(record: Dict[str, Any], sid: str, status: str) -> bool:
    return f"sid={sid} status={status}" in _log_text(record)


def append_call_log(svc: Any, opp_id: str, record: Dict[str, Any], note: str) -> bool:
    """Append one Activity Log line. False when the write did not land.

    A duplicate status for the same call SID is treated as already logged.
    """
    parts = note.split()
    sid = next((p.split("=", 1)[1] for p in parts if p.startswith("sid=")), "")
    status = next((p.split("=", 1)[1] for p in parts if p.startswith("status=")), "")
    if sid and status and _already_logged(record, sid, status):
        return True
    try:
        updated = svc.add_activity(opp_id, CALL_LOG_TYPE, note)
    except Exception as exc:  # noqa: BLE001
        log.warning("Activity Log append failed for a call: %s", _safe_twilio_error(exc))
        return False
    return updated is not None


def _url(path: str, lead_id: str, mode: str) -> str:
    query = urlencode({"lead_id": lead_id, "mode": mode})
    return f"{public_base()}{path}?{query}"


def place_call(record: Dict[str, Any], mode: Optional[str], svc: Any) -> Dict[str, Any]:
    """Ring Ryan (bridge) or the lead (message). Logs the queued call."""
    mode = normalize_mode(mode)
    missing = missing_settings()
    if missing:
        raise CallFailed("Missing on the API service: " + ", ".join(missing))
    lead_id = str(record.get("id") or "")
    if not _LEAD_RE.fullmatch(lead_id):
        raise CallBlocked(422, "This lead cannot be called from here.")
    phone = guard_call(record, mode, _now())
    caller = _e164(from_number())
    owner = _e164(owner_number())
    if not caller or not owner:
        raise CallFailed("Missing on the API service: TWILIO_FROM_NUMBER, OWNER_PHONE")
    target = owner if mode == "bridge" else phone
    params: Dict[str, Any] = {
        "to": target,
        "from_": caller,
        "url": _url("/api/twilio/voice/outbound-connect", lead_id, mode),
        "method": "POST",
        "status_callback": _url("/api/twilio/voice/outbound-status", lead_id, mode),
        "status_callback_method": "POST",
        "status_callback_event": ["initiated", "ringing", "answered", "completed"],
        "timeout": 25,
    }
    if mode == "message":
        params["machine_detection"] = "DetectMessageEnd"
    try:
        call = _client().calls.create(**params)
    except Exception as exc:  # noqa: BLE001
        log.warning("Outbound call was refused by Twilio: %s", _safe_twilio_error(exc))
        raise CallFailed("Twilio could not place the call. Nothing was logged as sent.") from exc
    sid = str(getattr(call, "sid", "") or "")
    status = str(getattr(call, "status", "") or "queued").lower()
    if not _SID_RE.fullmatch(sid) or not _STATUS_RE.fullmatch(status):
        log.warning("Twilio returned an unexpected call id or status")
        raise CallFailed("Twilio accepted the call but did not return a usable call id.")
    note = call_note(mode, sid, status)
    logged = append_call_log(svc, lead_id, record, note)
    result = {"ok": True, "mode": mode, "call_sid": sid, "status": status, "logged": logged}
    if not logged:
        result["warning"] = "Call placed, but the activity log could not be saved."
    return result


# ---------------------------------------------------------------- TwiML
def _say(text: str) -> str:
    voice = escape(say_voice(), _XML_ATTR)
    language = escape(say_language(), _XML_ATTR)
    return f'<Say language="{language}" voice="{voice}">{escape(text)}</Say>'


def _hangup(text: Optional[str] = None) -> str:
    body = _say(text) if text else ""
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}<Hangup/></Response>'


def _response(*parts: str) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><Response>' + "".join(parts) + "</Response>"


def _dial(number: str, caller_id: str) -> str:
    return (
        f'<Dial callerId="{escape(caller_id, _XML_ATTR)}" timeout="25" answerOnBridge="true">'
        f"<Number>{escape(number)}</Number></Dial>"
    )


def voicemail_text() -> str:
    spoken = format_phone(from_number()) or "the Shirtless Handyman"
    return VOICEMAIL_TEMPLATE.format(number=spoken)


def connect_twiml(record: Optional[Dict[str, Any]], mode: str, answered_by: str) -> str:
    """TwiML for the moment the first leg is answered."""
    if record is None or opt_out_reason(record):
        return _hangup()
    mode = mode if mode in MODES else ""
    if mode == "message" and message_blocked_reason(record):
        return _hangup()
    caller = _e164(from_number()) or ""
    if mode == "bridge":
        lead = lead_e164(record)
        if not lead or not caller:
            return _hangup()
        spoken = _CONNECTING.format(name=_speakable_name(record))
        return _response(_say(spoken), _dial(lead, caller), _say(_NO_ANSWER), "<Hangup/>")
    if mode != "message":
        return _hangup()
    answered = (answered_by or "").strip().lower()
    if answered == "fax":
        return _hangup()
    if answered in _MACHINE_ANSWERS:
        return _hangup(voicemail_text())
    lead_id = str(record.get("id") or "")
    action = escape(_url("/api/twilio/voice/outbound-gather", lead_id, "message"), _XML_ATTR)
    return _response(
        f'<Gather numDigits="1" action="{action}" method="POST" timeout="7">{_say(HUMAN_MESSAGE)}</Gather>',
        _say(_GOODBYE),
        "<Hangup/>",
    )


def gather_twiml(record: Optional[Dict[str, Any]], digits: str) -> str:
    """Press 1 connects the lead to Ryan. Anything else says goodbye."""
    if record is None or opt_out_reason(record) or message_blocked_reason(record):
        return _hangup()
    if (digits or "").strip() != "1":
        return _hangup(_GOODBYE)
    owner = _e164(owner_number())
    caller = _e164(from_number())
    if not owner or not caller:
        return _hangup()
    return _response(_say(_PRESSED), _dial(owner, caller), "<Hangup/>")


def signed_request_url(path: str, query: str) -> str:
    base = public_base()
    if not base:
        return ""
    url = f"{base}{path}"
    if query:
        url += "?" + query
    return url


def clean_sid(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text if _SID_RE.fullmatch(text) else None


def clean_status(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    return text if _STATUS_RE.fullmatch(text) else None


def clean_duration(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text or not text.isdigit() or len(text) > 6:
        return None
    return str(int(text))


def clean_lead_id(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text if _LEAD_RE.fullmatch(text) else None


def record_status(svc: Any, lead_id: str, mode: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Append status and duration from Twilio's callback. Sends nothing."""
    sid = clean_sid(params.get("CallSid"))
    status = clean_status(params.get("CallStatus"))
    if mode not in MODES or not sid or not status or not clean_lead_id(lead_id):
        return {"ok": False, "logged": False}
    record = svc.get(lead_id) if hasattr(svc, "get") else None
    if not record:
        return {"ok": False, "logged": False, "missing": True}
    duration = clean_duration(params.get("CallDuration"))
    note = call_note(mode, sid, status, duration)
    logged = append_call_log(svc, lead_id, record, note)
    return {"ok": True, "logged": logged}
