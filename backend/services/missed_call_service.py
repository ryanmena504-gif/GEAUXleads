"""Missed-call text: Ryan's cell forwards unanswered calls to a Twilio
number, Twilio asks this API what to do, and Ryan gets one text about who
called.

Flow (one call = at most one SMS, at most one paid research call):

1. Ryan's carrier forwards a no-answer / busy / unreachable call to the
   Twilio number (free conditional call forwarding on his cell plan).
2. Twilio POSTs the call to /api/twilio/voice/missed-call. The route checks
   the X-Twilio-Signature header (HMAC with TWILIO_AUTH_TOKEN) instead of
   the app password, answers right away with TwiML, and queues the work.
3. The work matches the caller's number against Contact phone / Phone
   number on the cached lead list (the same single-download reader every
   other screen uses; no extra Airtable pages).
4. No match: one Perplexity "caller_lookup" call, under a small daily cap,
   skipped for a number already looked up today, and switched off for the
   rest of the day after the first failure. Never retried.
5. One SMS to Ryan's cell through the Twilio REST API. Never retried; a
   failure is logged and the call is dropped.

This module never texts anyone except MISSED_CALL_NOTIFY_NUMBER (Ryan),
never writes to Airtable, and never creates a lead row. Make still creates
rows; the app still fills contacts.

Settings (Render > API service > Environment):
    TWILIO_ACCOUNT_SID          shared with Twilio Lookup
    TWILIO_AUTH_TOKEN           shared with Twilio Lookup; also signs webhooks
    MISSED_CALL_FROM_NUMBER     the Twilio number, +1504XXXXXXX
    MISSED_CALL_NOTIFY_NUMBER   Ryan's cell, +1504XXXXXXX
    MISSED_CALL_RESEARCH_DAILY_CAP   Perplexity lookups a day for unknown
                                callers (default 5, 0 turns research off)
    MISSED_CALL_TWIML_MODE      "say" (default: short message, then hang up)
                                or "reject" (busy signal, Twilio bills $0)
    MISSED_CALL_GREETING        words for "say" mode
    MISSED_CALL_WEBHOOK_URL     exact public URL Twilio calls; set it so the
                                signature check matches behind Render's proxy
    MISSED_CALL_APP_URL         frontend base for the lookup link
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from services.field_norm import format_phone, phone_digits

log = logging.getLogger("bloodhound.missed_call")

WEBHOOK_PATH = "/api/twilio/voice/missed-call"
NEW_ORLEANS = ZoneInfo("America/Chicago")
DEFAULT_APP_URL = "https://geauxleads-1.onrender.com"
DEFAULT_GREETING = (
    "Sorry I missed you. This is Ryan with The Shirtless Handyman. "
    "I got your number and will call you back shortly."
)
SMS_MAX_CHARS = 320  # two GSM segments; keeps each text at 1-2 billed segments

_PHONE_KEYS = ("contact_phone", "phone", "phone_number", "phone_alt")
_QUEUE_RANK = {"Ready to Contact": 0, "Contacted": 1}
_CALLER_LINE = re.compile(r"^\s*CALLER:\s*(.+?)\s*$", re.I | re.M)
_UNKNOWN_CALLER = {"unknown", "none", "n/a", "not found", "none found"}
_WITHHELD = ("anonymous", "unknown", "restricted", "private", "unavailable")


# ---------------------------------------------------------------- settings
def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def research_daily_cap() -> int:
    raw = _env("MISSED_CALL_RESEARCH_DAILY_CAP", "5")
    try:
        value = int(raw)
    except ValueError:
        return 5
    return max(0, min(value, 50))


def twiml_mode() -> str:
    return "reject" if _env("MISSED_CALL_TWIML_MODE").lower() == "reject" else "say"


def config_error() -> Optional[str]:
    """None when everything needed to text Ryan is set. Never echoes values."""
    missing = [
        name
        for name in (
            "TWILIO_ACCOUNT_SID",
            "TWILIO_AUTH_TOKEN",
            "MISSED_CALL_FROM_NUMBER",
            "MISSED_CALL_NOTIFY_NUMBER",
        )
        if not _env(name)
    ]
    if missing:
        return "Missing on the API service: " + ", ".join(missing)
    return None


# ---------------------------------------------------------------- signature
def webhook_url(request_url: str, headers: Any) -> str:
    """The URL Twilio signed.

    Render terminates TLS, so the app may see http:// while Twilio signed
    https://. MISSED_CALL_WEBHOOK_URL removes the guesswork; without it the
    forwarded proto header is used.
    """
    configured = _env("MISSED_CALL_WEBHOOK_URL")
    if configured:
        return configured
    proto = (headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    if proto and request_url.startswith("http://") and proto == "https":
        return "https://" + request_url[len("http://"):]
    return request_url


def signature_valid(url: str, params: Dict[str, str], signature: str) -> bool:
    token = _env("TWILIO_AUTH_TOKEN")
    if not token or not signature:
        return False
    try:
        from twilio.request_validator import RequestValidator  # type: ignore
    except ImportError:  # pragma: no cover
        log.error("twilio package missing; refusing missed-call webhook")
        return False
    return bool(RequestValidator(token).validate(url, params, signature))


# ---------------------------------------------------------------- TwiML
def twiml_response() -> str:
    if twiml_mode() == "reject":
        # Twilio does not answer or bill a call whose first verb is Reject.
        return '<?xml version="1.0" encoding="UTF-8"?><Response><Reject reason="busy"/></Response>'
    greeting = escape(_env("MISSED_CALL_GREETING", DEFAULT_GREETING)[:400])
    return (
        '<?xml version="1.0" encoding="UTF-8"?><Response>'
        f"<Say>{greeting}</Say><Hangup/></Response>"
    )


# ---------------------------------------------------------------- matching
def caller_digits(value: Any) -> Optional[str]:
    """10-digit NANP number, or None for a withheld / foreign / odd caller ID."""
    text = str(value or "").strip().lower()
    if not text or any(word in text for word in _WITHHELD):
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def match_leads(digits: Optional[str], leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Leads whose phone fields end in the same 10 digits, most actionable first."""
    if not digits:
        return []
    found = []
    for lead in leads:
        for key in _PHONE_KEYS:
            raw = re.sub(r"\D", "", str(lead.get(key) or ""))
            candidate = phone_digits(lead.get(key)) or ""
            # A cell holding two numbers ("504-... / 985-...") still matches.
            if (candidate and candidate[-10:] == digits) or (len(raw) > 11 and digits in raw):
                found.append(lead)
                break
    found.sort(key=lambda o: (
        _QUEUE_RANK.get(str(o.get("current_queue") or "").strip(), 9),
        -(o.get("governed_priority_score") or 0),
    ))
    return found


# ---------------------------------------------------------------- research budget
class ResearchBudget:
    """Per-day cap, one lookup per number per day, stop after a failure.

    In memory: a Render restart resets the count, which can only lower
    spend that day by at most one cap's worth. Good enough at 5 a day.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day = ""
        self._used = 0
        self._numbers: Dict[str, Optional[str]] = {}
        self._tripped = False

    def _roll(self, day: str) -> None:
        if day != self._day:
            self._day, self._used, self._numbers, self._tripped = day, 0, {}, False

    def claim(self, digits: str, day: str, cap: int) -> str:
        """'ok' to spend one call, otherwise the reason it is skipped."""
        with self._lock:
            self._roll(day)
            if cap <= 0:
                return "research off"
            if self._tripped:
                return "paused after a failed lookup today"
            if digits in self._numbers:
                return "already looked up today"
            if self._used >= cap:
                return f"daily cap of {cap} reached"
            self._used += 1
            self._numbers[digits] = None
            return "ok"

    def remember(self, digits: str, day: str, caller: Optional[str]) -> None:
        with self._lock:
            self._roll(day)
            self._numbers[digits] = caller

    def cached(self, digits: str, day: str) -> Optional[str]:
        with self._lock:
            self._roll(day)
            return self._numbers.get(digits)

    def trip(self, day: str) -> None:
        with self._lock:
            self._roll(day)
            self._tripped = True


_budget = ResearchBudget()
_seen_calls: Dict[str, bool] = {}
_seen_lock = threading.Lock()


def first_time_seen(call_sid: str) -> bool:
    """Twilio can re-send a webhook; only the first one does any work."""
    if not call_sid:
        return True
    with _seen_lock:
        if call_sid in _seen_calls:
            return False
        if len(_seen_calls) > 2000:
            _seen_calls.clear()
        _seen_calls[call_sid] = True
        return True


def parse_caller(answer: str) -> Optional[str]:
    m = _CALLER_LINE.search(answer or "")
    if not m:
        return None
    name = m.group(1).strip().strip(".").strip()
    if not name or name.lower() in _UNKNOWN_CALLER:
        return None
    return name[:80]


# ---------------------------------------------------------------- SMS text
def _first(lead: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = lead.get(key)
        if isinstance(value, (list, tuple)):
            value = next((v for v in value if v), None)
        if value not in (None, "", 0):
            return str(value).strip()
    return ""


def _clip(text: str, limit: int = SMS_MAX_CHARS) -> str:
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_sms(
    *,
    caller: str,
    digits: Optional[str],
    when: datetime,
    lead: Optional[Dict[str, Any]] = None,
    extra_matches: int = 0,
    carrier_name: str = "",
    research_name: Optional[str] = None,
    research_note: str = "",
    app_url: str = "",
) -> str:
    stamp = when.astimezone(NEW_ORLEANS).strftime("%-I:%M %p")
    shown = format_phone(digits) if digits else (caller or "a hidden number")
    lines = [f"Missed call {stamp} CT from {shown}"]
    if lead:
        who = _first(lead, "decision_maker", "owner", "name") or "a lead"
        lines.append(f"GEAUXleads: {who}")
        place = _first(lead, "project_address", "address")
        if place:
            lines.append(place)
        bits = [b for b in (
            _first(lead, "project_type"),
            _first(lead, "status", "current_queue"),
        ) if b]
        if bits:
            lines.append(" · ".join(bits))
        if extra_matches:
            lines.append(f"+{extra_matches} more lead(s) with this number")
    else:
        lines.append("Not in GEAUXleads")
        if carrier_name:
            lines.append(f"Caller ID name: {carrier_name}")
        if research_name:
            lines.append(f"Web: {research_name}")
        elif research_note:
            lines.append(research_note)
    if digits and app_url:
        lines.append(f"{app_url.rstrip('/')}/lookup?phone=%2B1{digits}")
    return _clip("\n".join(lines))


# ---------------------------------------------------------------- send
def send_sms(body: str) -> Optional[str]:
    """One REST call. Returns the message SID, or None after logging a failure."""
    try:
        from twilio.http.http_client import TwilioHttpClient  # type: ignore
        from twilio.rest import Client  # type: ignore

        client = Client(
            _env("TWILIO_ACCOUNT_SID"),
            _env("TWILIO_AUTH_TOKEN"),
            # max_retries=0 pinned so the HTTP layer never re-sends a paid
            # text, whatever a future SDK default becomes.
            http_client=TwilioHttpClient(timeout=15, max_retries=0),
        )
        msg = client.messages.create(
            to=_env("MISSED_CALL_NOTIFY_NUMBER"),
            from_=_env("MISSED_CALL_FROM_NUMBER"),
            body=body,
        )
        return getattr(msg, "sid", None)
    except Exception as e:  # noqa: BLE001 - log and stop, never retry
        log.warning("Missed-call SMS failed, not retrying: %s %s",
                    type(e).__name__, str(e)[:200])
        return None


# ---------------------------------------------------------------- the job
ResearchFn = Callable[[str, str], Awaitable[Dict[str, Any]]]
LeadsFn = Callable[[], Awaitable[List[Dict[str, Any]]]]
SendFn = Callable[[str], Optional[str]]


async def handle_missed_call(
    params: Dict[str, str],
    *,
    load_leads: LeadsFn,
    research: Optional[ResearchFn],
    send: Optional[SendFn] = None,
    now: Optional[datetime] = None,
    budget: Optional[ResearchBudget] = None,
) -> Dict[str, Any]:
    """Match, maybe research once, text Ryan once. Returns what happened."""
    budget = budget or _budget
    send = send or send_sms
    now = now or datetime.now(NEW_ORLEANS)
    day = now.astimezone(NEW_ORLEANS).date().isoformat()
    caller = str(params.get("From") or "")
    digits = caller_digits(caller)
    result: Dict[str, Any] = {"call_sid": params.get("CallSid"), "matched": 0,
                              "researched": False, "sms_sid": None}

    notify = caller_digits(_env("MISSED_CALL_NOTIFY_NUMBER"))
    if digits and notify and digits == notify:
        # Carrier sent Ryan's own number as caller ID: forwarding hid the
        # real caller. Say so instead of looking Ryan up.
        body = _clip(
            f"Missed call {now.astimezone(NEW_ORLEANS).strftime('%-I:%M %p')} CT. "
            "Your carrier passed your own number as caller ID, so the real "
            "caller is hidden. Check your recent calls."
        )
        result["sms_sid"] = send(body)
        result["outcome"] = "caller id hidden by forwarding"
        return result

    leads: List[Dict[str, Any]] = []
    if digits:
        try:
            leads = await load_leads()
        except Exception as e:  # noqa: BLE001
            log.warning("Missed-call lead lookup failed: %s", str(e)[:200])
    matches = match_leads(digits, leads)
    result["matched"] = len(matches)

    research_name: Optional[str] = None
    research_note = ""
    if not matches and digits:
        research_name = budget.cached(digits, day)
        if research_name is None:
            verdict = budget.claim(digits, day, research_daily_cap()) if research else "research off"
            if verdict == "ok":
                result["researched"] = True
                try:
                    out = await research("caller_lookup", f"+1{digits}")  # type: ignore[misc]
                    research_name = parse_caller(out.get("answer") or "")
                    budget.remember(digits, day, research_name)
                    if not research_name:
                        research_note = "Web: nothing public on this number"
                except Exception as e:  # noqa: BLE001 - one try, then stop for the day
                    budget.trip(day)
                    log.warning("Missed-call research failed, not retrying: %s %s",
                                type(e).__name__, str(e)[:200])
                    research_note = "Web lookup failed (not retried)"
            elif verdict != "already looked up today":
                research_note = f"Web lookup skipped: {verdict}"

    body = build_sms(
        caller=caller,
        digits=digits,
        when=now,
        lead=matches[0] if matches else None,
        extra_matches=max(0, len(matches) - 1),
        carrier_name=str(params.get("CallerName") or "").strip(),
        research_name=research_name,
        research_note=research_note,
        app_url=_env("MISSED_CALL_APP_URL", DEFAULT_APP_URL),
    )
    result["sms_sid"] = send(body)
    result["outcome"] = "matched" if matches else "unknown caller"
    return result
