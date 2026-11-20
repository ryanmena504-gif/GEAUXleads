"""Append-only log of contact-research attempts.

Each attempt is one line in the Activity Log, the journal this app
already writes:

    2026-11-20T15:04:00+00:00 | enrichment_attempt | {"found":{},"result":"not_found","source":"perplexity:homeowner_lookup"}

The line records when the lookup ran, which method ran, and whether it
found a contact. `found` lists whatever came back (name, phone, email,
mailing address), including on a not-found result.

Existing leads have no such lines. They read as an empty history. That
is the safe default: zero attempts, and a lead is not dropped for lack
of a phone or email until two attempts are on the record and both failed.
Nothing here creates, renames, or deletes an Airtable field, and nothing
here deletes a lead.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

ATTEMPT_TYPE = "enrichment_attempt"
ATTEMPT_LIMIT = 2

RESULT_FOUND = "found"
RESULT_NOT_FOUND = "not_found"
RESULT_FAILED = "failed"

# Returned by enrichment_skip_reason. The morning batch drops a lead on
# this reason without spending another credit.
SKIP_EXHAUSTED = "attempts exhausted"
# Every supported method is already on the lead. Log it, and do not
# spend a credit or add another attempt line.
SKIP_METHODS = "all methods tried"
SKIPPED_TYPE = "enrichment_skipped"

_FOUND_KEYS = ("name", "phone", "email", "mailing_address")
_FAILED_RESULTS = {RESULT_NOT_FOUND, RESULT_FAILED}
_RESULT_LABELS = {
    RESULT_FOUND: "found",
    RESULT_NOT_FOUND: "not found",
    RESULT_FAILED: "failed",
}


def _clean_found(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    found: Dict[str, str] = {}
    for key in _FOUND_KEYS:
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            found[key] = item.strip()
    return found


def _attempt_from_note(timestamp: str, note: str) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(note)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return {
        "timestamp": timestamp,
        "source": str(payload.get("source") or ""),
        "result": str(payload.get("result") or RESULT_NOT_FOUND),
        "found": _clean_found(payload.get("found")),
    }


def parse_attempts(text: Any) -> List[Dict[str, Any]]:
    """Attempt history in log order. Malformed lines are ignored."""
    if not isinstance(text, str) or not text.strip():
        return []
    attempts: List[Dict[str, Any]] = []
    for line in text.splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        timestamp, type_, note = (part.strip() for part in parts)
        if type_ != ATTEMPT_TYPE or not timestamp:
            continue
        attempt = _attempt_from_note(timestamp, note)
        if attempt:
            attempts.append(attempt)
    return attempts


def current_log(opp: Dict[str, Any]) -> str:
    """The journal text on a lead. Empty when the lead has never been logged."""
    raw = opp.get("activity_log_raw")
    if isinstance(raw, str) and raw.strip():
        return raw
    alt = opp.get("activity_log")
    if isinstance(alt, str):
        return alt
    return ""


def attempts_of(opp: Dict[str, Any]) -> List[Dict[str, Any]]:
    return parse_attempts(current_log(opp))


def append_attempt(existing: Any, attempt: Dict[str, Any]) -> str:
    """Return the journal with one new attempt line. Does not write."""
    payload = {
        "source": str(attempt.get("source") or ""),
        "result": str(attempt.get("result") or RESULT_NOT_FOUND),
        "found": _clean_found(attempt.get("found")),
    }
    line = (
        f"{str(attempt.get('timestamp') or '').strip()} | {ATTEMPT_TYPE} | "
        f"{json.dumps(payload, separators=(',', ':'), sort_keys=True)}"
    )
    current = existing.strip() if isinstance(existing, str) else ""
    return f"{current}\n{line}" if current else line


def counted_attempts(attempts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One attempt per method. A repeated method is not a new attempt."""
    seen = set()
    counted: List[Dict[str, Any]] = []
    for attempt in attempts:
        source = str(attempt.get("source") or "")
        if source in seen:
            continue
        seen.add(source)
        counted.append(attempt)
    return counted


def failed_attempt_count(attempts: List[Dict[str, Any]]) -> int:
    counted = counted_attempts(attempts)
    return sum(1 for attempt in counted if attempt.get("result") in _FAILED_RESULTS)


def should_drop_for_no_contact(
    opp: Dict[str, Any],
    attempts: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """True only when two different methods failed to find a phone or email.

    A second run of a method already on the lead does not count. Fewer
    than two failed attempts is not a drop, even when Enrichment status
    already says no contact was found. A phone or email on the lead is
    not a drop either.
    """
    history = counted_attempts(attempts if attempts is not None else attempts_of(opp))
    if len(history) < ATTEMPT_LIMIT or failed_attempt_count(history) < ATTEMPT_LIMIT:
        return False
    from services.field_norm import is_valid_email, is_valid_phone, resolved_email, resolved_phone

    if is_valid_phone(resolved_phone(opp)) or is_valid_email(resolved_email(opp)):
        return False
    return True


def drop_field_updates(
    opp: Dict[str, Any],
    attempts: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Status fields to write when the lead should leave the contact queue.

    Empty when the lead should stay. Does not delete the record. An
    address-only lead keeps its mail-door tag because that tag is derived
    from the project, not from this status.
    """
    if not should_drop_for_no_contact(opp, attempts):
        return {}
    fields: Dict[str, Any] = {}
    status = str(opp.get("status") or opp.get("status_raw") or "")
    if status not in {"Won", "Lost", "Disqualified"}:
        fields["status"] = "Disqualified"
    outcome = str(opp.get("outcome") or "").strip().lower()
    if outcome in {"", "pending", "no usable contact"}:
        fields["outcome"] = "No usable contact"
    return fields


def describe_attempt(attempt: Dict[str, Any]) -> str:
    """One plain sentence for the activity timeline."""
    result = str(attempt.get("result") or RESULT_NOT_FOUND)
    label = _RESULT_LABELS.get(result, result.replace("_", " "))
    found = _clean_found(attempt.get("found"))
    titles = {
        "name": "name",
        "phone": "phone",
        "email": "email",
        "mailing_address": "mailing address",
    }
    bits = [f"{titles[key]} {found[key]}" for key in _FOUND_KEYS if found.get(key)]
    if bits:
        detail = ", ".join(bits)
    elif result == RESULT_FOUND:
        detail = "contact found"
    elif result == RESULT_FAILED:
        detail = "lookup failed"
    else:
        detail = "nothing found"
    source = attempt.get("source") or "unknown method"
    return f"Enrichment via {source}: {label}. {detail}."


def describe_attempt_note(note: str) -> str:
    """Human text for an attempt line. Unparseable notes are left as written."""
    attempt = _attempt_from_note("", note)
    if attempt is None:
        return note
    return describe_attempt(attempt)


def annotate_enrichment_attempts(opp: Dict[str, Any]) -> Dict[str, Any]:
    """Attach `enrichment_attempts` for the API. Missing history is []."""
    opp["enrichment_attempts"] = attempts_of(opp)
    return opp


def methods_exhausted_message(methods: Sequence[str]) -> str:
    listed = ", ".join(methods) if methods else "the available lookups"
    return (
        f"Every enrichment method has already been tried ({listed}). "
        "This was not counted as a new attempt."
    )


def skipped_attempt_fields(
    opp: Dict[str, Any],
    methods: Sequence[str],
    *,
    today: str,
    attempted_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Journal line for a refused repeat. Empty when that line is already there.

    The line is not an enrichment attempt, so it does not move the lead
    closer to the two-attempt drop.
    """
    message = methods_exhausted_message(methods)
    log = current_log(opp)
    if message in log:
        return {}
    stamp = attempted_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    line = f"{stamp} | {SKIPPED_TYPE} | {message}"
    new_log = f"{log}\n{line}" if log else line
    prior = opp.get("notes")
    prior_text = prior.strip() if isinstance(prior, str) else ""
    note = f"Contact Finder ({(today or '')[:10]}): {message}"
    notes = f"{prior_text}\n\n{note}" if prior_text else note
    return {"activity_log": new_log, "notes": notes}
