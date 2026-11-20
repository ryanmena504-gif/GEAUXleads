"""Shared rules for outbound calls and texts.

Ryan taps Call or Text, or a script posts with the app password. Nothing
here runs on a timer. Twilio credentials are read from the environment and
never written to logs, responses, or the Activity Log.

No Airtable field is created. STOP is recorded on the Activity Log and on
Notes, which already exist. SMS Permission stays read-only.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from services.field_norm import is_valid_phone, phone_digits, resolved_phone

log = logging.getLogger("bloodhound.outbound")

CHICAGO = ZoneInfo("America/Chicago")
STOP_LINE = "Reply STOP to opt out"
OPT_OUT_MARKER = "SMS opt-out: STOP"
CALL_OPEN, CALL_CLOSE = 9, 18   # 9:00am inclusive, 6:00pm exclusive
TEXT_OPEN, TEXT_CLOSE = 9, 20   # 9:00am inclusive, 8:00pm exclusive

_STOP_LINE_RE = re.compile(r"reply\s+stop\s+to\s+opt\s+out", re.I)
_EXACT_STOP = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit"}
_EXACT_START = {"start", "unstop", "yes"}
_STOP_WORD = re.compile(r"\b(stop|stopall|unsubscribe)\b", re.I)
_OPT_OUT_TOKENS = (
    "do not contact",
    "do not call",
    "opted out",
    "opt out",
    "unsubscribed",
    "dnc",
)
_OPT_OUT_FIELDS = (
    "status",
    "status_raw",
    "approval_status",
    "outreach_status",
    "hunt_status",
    "risk_flags",
    "sms_permission",
    "contact_consent",
    "call_consent",
    "do_not_call",
    "dnc",
    "opt_out",
    "opted_out",
)
_BOOL_FLAGS = ("do_not_call", "dnc", "opt_out", "opted_out")
_TZ_ALIASES = {
    "ct": "America/Chicago", "cst": "America/Chicago", "cdt": "America/Chicago",
    "central": "America/Chicago",
    "et": "America/New_York", "est": "America/New_York", "edt": "America/New_York",
    "eastern": "America/New_York",
    "pt": "America/Los_Angeles", "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles",
    "pacific": "America/Los_Angeles",
    "mt": "America/Denver", "mst": "America/Denver", "mdt": "America/Denver",
    "mountain": "America/Denver",
}
_CALL_STATUSES = {
    "queued", "initiated", "ringing", "in-progress", "answered", "completed",
    "busy", "failed", "no-answer", "canceled", "cancelled",
    "owner_voicemail", "voicemail", "connecting", "unknown",
}
_TEXT_STATUSES = {
    "queued", "accepted", "sending", "sent", "delivered", "undelivered",
    "failed", "received", "unknown",
}


class ContactRefused(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ProviderError(Exception):
    """Twilio did not accept the request. The message never includes secrets."""

    def __init__(self, message: str = "Twilio did not complete the request."):
        super().__init__(message)
        self.message = message


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def current_time() -> datetime:
    return datetime.now(timezone.utc)


def to_e164(value: Any) -> Optional[str]:
    if not is_valid_phone(value):
        return None
    digits = phone_digits(value)
    if not digits:
        return None
    return "+1" + digits


def lead_e164(record: Dict[str, Any]) -> Optional[str]:
    raw = resolved_phone(record) or ""
    parts = re.split(r"\s*(?:/|;|,|\bor\b)\s*", raw, flags=re.I)
    for part in parts:
        number = to_e164(part)
        if number:
            return number
    return to_e164(raw)


def from_number() -> Optional[str]:
    """Shop caller ID. TWILIO_FROM_NUMBER wins; the missed-call number is the fallback."""
    for name in ("TWILIO_FROM_NUMBER", "MISSED_CALL_FROM_NUMBER"):
        number = to_e164(env(name))
        if number:
            return number
    return None


def owner_number() -> Optional[str]:
    """Ryan's phone. OWNER_PHONE, then LEAD_NOTIFICATION_PHONE, then the missed-call notify number."""
    for name in ("OWNER_PHONE", "LEAD_NOTIFICATION_PHONE", "MISSED_CALL_NOTIFY_NUMBER"):
        number = to_e164(env(name))
        if number:
            return number
    return None


def public_base() -> str:
    base = env("PUBLIC_BACKEND_URL").rstrip("/")
    if base.startswith("http://") or base.startswith("https://"):
        return base
    webhook = env("MISSED_CALL_WEBHOOK_URL")
    if not webhook:
        return ""
    parts = urlsplit(webhook)
    if parts.scheme in ("http", "https") and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}"
    return ""


def public_url(path: str, query: str = "") -> str:
    base = public_base()
    if not base:
        return ""
    url = base + path
    if query:
        url += "?" + query
    return url


def config_error(*, need_owner: bool) -> Optional[str]:
    """Names of missing settings. Never includes a value."""
    missing = []
    if not env("TWILIO_ACCOUNT_SID"):
        missing.append("TWILIO_ACCOUNT_SID")
    if not env("TWILIO_AUTH_TOKEN"):
        missing.append("TWILIO_AUTH_TOKEN")
    if not from_number():
        if env("TWILIO_FROM_NUMBER") or env("MISSED_CALL_FROM_NUMBER"):
            missing.append("TWILIO_FROM_NUMBER (a usable US number)")
        else:
            missing.append("TWILIO_FROM_NUMBER")
    if need_owner and not owner_number():
        if any(env(name) for name in ("OWNER_PHONE", "LEAD_NOTIFICATION_PHONE", "MISSED_CALL_NOTIFY_NUMBER")):
            missing.append("OWNER_PHONE or LEAD_NOTIFICATION_PHONE (a usable US number)")
        else:
            missing.append("OWNER_PHONE or LEAD_NOTIFICATION_PHONE")
    if not public_base():
        missing.append("PUBLIC_BACKEND_URL")
    if missing:
        return "Missing on the API service: " + ", ".join(missing)
    return None


def twilio_client():
    from twilio.http.http_client import TwilioHttpClient  # type: ignore
    from twilio.rest import Client  # type: ignore

    return Client(
        env("TWILIO_ACCOUNT_SID"),
        env("TWILIO_AUTH_TOKEN"),
        http_client=TwilioHttpClient(timeout=20, max_retries=0),
    )


def log_provider(kind: str, exc: Exception) -> None:
    """Log the failure type and Twilio's status code. Not the exception text."""
    log.warning(
        "%s failed: %s status=%s code=%s",
        kind,
        type(exc).__name__,
        getattr(exc, "status", None),
        getattr(exc, "code", None),
    )


def signature_ok(url: str, params: Dict[str, str], signature: str) -> bool:
    from services.missed_call_service import signature_valid
    return signature_valid(url, params, signature)


def safe_id(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "", str(value or ""))[:64]


def safe_sid(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or ""))[:40]


def lead_zone(record: Dict[str, Any]) -> ZoneInfo:
    raw = ""
    for key in ("timezone", "time_zone", "local_timezone"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            raw = value.strip()
            break
    if not raw:
        return CHICAGO
    key = _TZ_ALIASES.get(raw.lower(), raw)
    try:
        return ZoneInfo(key)
    except Exception:
        log.warning("Lead timezone %r is not a zone name; using America/Chicago", raw[:40])
        return CHICAGO


def local_now(record: Dict[str, Any], now: Optional[datetime] = None) -> datetime:
    when = now or current_time()
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(lead_zone(record))


def within_window(local: datetime, open_hour: int, close_hour: int) -> bool:
    """Monday–Saturday, open_hour inclusive through close_hour exclusive. Sunday is closed."""
    if local.weekday() == 6:
        return False
    minutes = local.hour * 60 + local.minute
    return open_hour * 60 <= minutes < close_hour * 60


def window_message(local: datetime, zone: ZoneInfo, close_hour: int, channel: str) -> str:
    end = "6pm" if close_hour == 18 else "8pm"
    kind = "Calls" if channel == "call" else "Texts"
    clock = local.strftime("%A %-I:%M %p")
    return (
        f"It's {clock} in {zone.key}. "
        f"{kind} go out Monday through Saturday, 9am to {end} local time."
    )


def is_public_record_lead(record: Dict[str, Any]) -> bool:
    from services.mail_door import is_permit_or_sale
    if is_permit_or_sale(record):
        return True
    blob = " ".join(
        str(record.get(key) or "") for key in ("source", "source_category")
    ).lower().replace("_", " ").replace("-", " ")
    return "public record" in blob or "assessor" in blob


def has_consent(record: Dict[str, Any]) -> bool:
    from services.mail_door import has_phone_consent
    return has_phone_consent(record)


def _blob(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(_blob(item) for item in value)
    return str(value).lower().replace("_", " ").replace("-", " ")


def _activity_lines(record: Dict[str, Any]) -> list:
    lines = []
    raw = record.get("activity_log_raw") or record.get("activity_log") or ""
    lines.extend(str(raw).splitlines())
    for item in record.get("activity_timeline") or []:
        if isinstance(item, dict):
            lines.append(f"{item.get('type') or ''} | {item.get('note') or ''}")
    return lines


def latest_stop_state(record: Dict[str, Any]) -> Optional[str]:
    """'out', 'in', or None. The latest STOP / START line wins."""
    state = None
    for line in _activity_lines(record):
        low = line.lower()
        if "sms_opt_in" in low:
            state = "in"
        elif "sms_opt_out" in low:
            state = "out"
    return state


def opt_out_message(record: Dict[str, Any]) -> Optional[str]:
    """Why this lead cannot be called or texted, or None."""
    from services.outreach_policy import do_not_contact_message
    if do_not_contact_message(record):
        return "This lead is marked Do Not Contact. Nothing was sent."
    for key in _BOOL_FLAGS:
        if record.get(key) is True:
            return "This lead is opted out. Nothing was sent."
    for key in _OPT_OUT_FIELDS:
        text = _blob(record.get(key))
        if text and any(token in text for token in _OPT_OUT_TOKENS):
            return "This lead is opted out. Nothing was sent."
    state = latest_stop_state(record)
    if state == "out":
        return "This lead texted STOP. Nothing was sent."
    if state == "in":
        return None
    if OPT_OUT_MARKER in str(record.get("notes") or ""):
        return "This lead is opted out of texts. Nothing was sent."
    return None


def assert_call_allowed(record: Dict[str, Any], mode: str, now: Optional[datetime] = None) -> None:
    mode = (mode or "").strip().lower()
    if mode not in ("bridge", "message"):
        raise ContactRefused("bad_mode", "Mode must be bridge or message.")
    if not lead_e164(record):
        raise ContactRefused("no_phone", "This lead has no usable phone number.")
    refused = opt_out_message(record)
    if refused:
        raise ContactRefused("opted_out", refused)
    if mode == "message" and is_public_record_lead(record) and not has_consent(record):
        raise ContactRefused(
            "needs_consent",
            "Automated voice messages aren't allowed on a permit or public-record "
            "lead without a consent flag. Bridge mode can still connect you live.",
        )
    zone = lead_zone(record)
    local = local_now(record, now)
    if not within_window(local, CALL_OPEN, CALL_CLOSE):
        raise ContactRefused(
            "outside_calling_window",
            window_message(local, zone, CALL_CLOSE, "call"),
        )


def assert_text_allowed(record: Dict[str, Any], now: Optional[datetime] = None) -> None:
    if not lead_e164(record):
        raise ContactRefused("no_phone", "This lead has no usable phone number.")
    refused = opt_out_message(record)
    if refused:
        raise ContactRefused("opted_out", refused)
    if is_public_record_lead(record) and not has_consent(record):
        raise ContactRefused(
            "needs_consent",
            "Texts aren't allowed on a permit or public-record lead without a consent flag.",
        )
    zone = lead_zone(record)
    local = local_now(record, now)
    if not within_window(local, TEXT_OPEN, TEXT_CLOSE):
        raise ContactRefused(
            "outside_texting_window",
            window_message(local, zone, TEXT_CLOSE, "text"),
        )


def ensure_stop_line(body: str) -> str:
    text = (body or "").strip()
    if _STOP_LINE_RE.search(text):
        return text[:1600]
    suffix = "\n\n" + STOP_LINE
    room = 1600 - len(suffix)
    if len(text) > room:
        text = text[:room].rstrip()
    if not text:
        return STOP_LINE
    return text + suffix


def inbound_keyword(body: str) -> Optional[str]:
    """'stop', 'start', or None. STOP/unsubscribe in the message opts out.

    START, UNSTOP, and a message that is only YES opt back in. A longer
    reply that merely contains 'yes' does not.
    """
    text = (body or "").strip().lower()
    compact = re.sub(r"[^a-z]", "", text)
    if compact in _EXACT_START:
        return "start"
    if compact in _EXACT_STOP or _STOP_WORD.search(text):
        return "stop"
    return None


def _status(value: str, allowed: set) -> str:
    text = (value or "").strip().lower()
    return text if text in allowed else "unknown"


def call_note(*, mode: str, sid: str, status: str, duration: Any = None) -> str:
    clean_mode = mode if mode in ("bridge", "message") else "bridge"
    clean_status = _status(status, _CALL_STATUSES)
    parts = [f"mode={clean_mode}", f"sid={safe_sid(sid)}", f"status={clean_status}"]
    if duration is not None and re.fullmatch(r"\d{1,6}", str(duration).strip()):
        parts.append(f"duration={int(str(duration).strip())}s")
    return " ".join(parts)


def text_note(*, sid: str, status: str, body: Optional[str] = None) -> str:
    clean_status = _status(status, _TEXT_STATUSES)
    parts = [f"sid={safe_sid(sid)}", f"status={clean_status}"]
    if body is not None:
        flat = " ".join(str(body).split())
        if len(flat) > 1600:
            flat = flat[:1600] + "..."
        parts.append("body=" + flat)
    return " ".join(parts)


def _already(record: Optional[Dict[str, Any]], needle: str) -> bool:
    """True when every token in needle is its own word on one log line.

    Token match stops sid=SM1 from counting as sid=SM12.
    """
    tokens = (needle or "").split()
    if not record or not tokens:
        return False
    for line in _activity_lines(record):
        # The text body is logged after " body=" and can contain any words.
        head = line.split(" body=", 1)[0]
        words = head.split()
        if all(token in words for token in tokens):
            return True
    return False


def remember(svc: Any, lead_id: str, kind: str, note: str, needle: str = "") -> bool:
    """Append one Activity Log line. A repeated sid+status is left as-is."""
    try:
        current = svc.get(lead_id) if hasattr(svc, "get") else None
    except Exception as exc:  # noqa: BLE001
        log.warning("Activity Log read failed for %s: %s", lead_id, type(exc).__name__)
        current = None
    if needle and _already(current, needle):
        return True
    try:
        svc.add_activity(lead_id, kind, note)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Activity Log append failed for %s: %s", lead_id, type(exc).__name__)
        return False


def _write_notes(svc: Any, lead_id: str, notes: str) -> None:
    try:
        svc.update_fields(lead_id, {"notes": notes})
    except Exception as exc:  # noqa: BLE001
        log.warning("Notes update failed for %s: %s", lead_id, type(exc).__name__)


def mark_sms_opt_out(svc: Any, lead_id: str, sid: str = "") -> None:
    """Record STOP on the Activity Log and on Notes. Does not create a field."""
    clean = safe_sid(sid)
    note = "inbound STOP" + (f" sid={clean}" if clean else "")
    needle = f"sid={clean}" if clean else "sms_opt_out"
    remember(svc, lead_id, "sms_opt_out", note, needle=needle)
    try:
        lead = svc.get(lead_id) or {}
    except Exception:  # noqa: BLE001
        lead = {}
    notes = str(lead.get("notes") or "")
    if OPT_OUT_MARKER not in notes:
        _write_notes(svc, lead_id, (notes + "\n" + OPT_OUT_MARKER).strip())


def mark_sms_opt_in(svc: Any, lead_id: str, sid: str = "") -> None:
    clean = safe_sid(sid)
    note = "inbound START" + (f" sid={clean}" if clean else "")
    needle = f"sid={clean}" if clean else ""
    remember(svc, lead_id, "sms_opt_in", note, needle=needle)
    try:
        lead = svc.get(lead_id) or {}
    except Exception:  # noqa: BLE001
        lead = {}
    notes = str(lead.get("notes") or "")
    if OPT_OUT_MARKER in notes:
        kept = [line for line in notes.splitlines() if line.strip() != OPT_OUT_MARKER]
        _write_notes(svc, lead_id, "\n".join(kept).strip())
