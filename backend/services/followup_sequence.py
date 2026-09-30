"""Four-touch outreach sequence.

Every lead gets up to 4 outreach attempts, then the sequence is done and the
lead becomes Lost. State lives in Airtable on two columns:

- `Outreach attempt` (Number) — touches logged so far, 0-4. Ryan adds this
  column by hand; the app never creates Airtable fields.
- `Next followup` (Date, existing) — when the next touch is due. The Missions
  page already surfaces Contacted leads whose Next followup is today or
  earlier, so driving the sequence through this column wires follow-ups into
  the existing daily workflow with no extra UI.

The sequence (attempt = the touch being logged):
  1. Email            → next touch due in 3 days
  2. Call + text      → next touch due in 4 days  (day 7)
  3. Follow-up email  → next touch due in 7 days  (day 14)
  4. Breakup email    → sequence complete → Status = Lost

Touch 1 is the first-contact send ("I sent it"). Touches 2-4 are logged from
the Contacted follow-up panel. A reply at any point moves the lead out of the
sequence via the normal outcome buttons ("They replied" / "Estimate
requested"); "Not interested" also exits. Attempt 4 closes the lead because
the breakup email is the last touch — if they reply later, Ryan re-opens by
resetting `Outreach attempt` in Airtable.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Optional

MAX_ATTEMPTS = 4

# Days to wait AFTER touch N before touch N+1 is due. Touch 4 has no
# successor — logging it closes the lead.
TOUCH_INTERVAL_DAYS: Dict[int, int] = {1: 3, 2: 4, 3: 7}

TOUCH_LABELS: Dict[int, str] = {
    1: "Email",
    2: "Call + text",
    3: "Follow-up email",
    4: "Breakup email",
}

# Channel values accepted by POST /opportunities/{id}/result.
TOUCH_CHANNELS: Dict[int, str] = {
    1: "Email",
    2: "Call",
    3: "Email",
    4: "Email",
}


def coerce_attempt(value: Any) -> int:
    """Touches logged so far, clamped to 0..MAX_ATTEMPTS. Garbage → 0."""
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return 0
    return max(0, min(MAX_ATTEMPTS, n))


def next_touch(attempt: Any) -> Optional[Dict[str, Any]]:
    """Describe the NEXT touch due given touches logged so far.

    Returns None when the sequence is complete (attempt >= MAX_ATTEMPTS).
    """
    done = coerce_attempt(attempt)
    if done >= MAX_ATTEMPTS:
        return None
    n = done + 1
    return {
        "attempt": n,
        "of": MAX_ATTEMPTS,
        "label": TOUCH_LABELS[n],
        "channel": TOUCH_CHANNELS[n],
    }


def advance(attempt: Any, today: Optional[date] = None) -> Dict[str, Any]:
    """Compute the Airtable writes for logging one touch.

    Returns a dict with:
      outreach_attempt — the new touch count (1..4)
      next_follow_up   — ISO date string for the following touch, or None
                         when the sequence just completed
      closes_lead      — True when this touch was #4 (caller sets Lost)
      next             — next_touch() AFTER this touch (None when complete)
    """
    today = today or date.today()
    done = coerce_attempt(attempt)
    if done >= MAX_ATTEMPTS:
        raise ValueError("Sequence complete — no further touches allowed")
    new_attempt = done + 1
    closes = new_attempt >= MAX_ATTEMPTS
    interval = TOUCH_INTERVAL_DAYS.get(new_attempt)
    return {
        "outreach_attempt": new_attempt,
        "next_follow_up": None if closes or interval is None
        else (today + timedelta(days=interval)).isoformat(),
        "closes_lead": closes,
        "next": next_touch(new_attempt),
    }


def due_for_touch(record: Dict[str, Any], today: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """Is this Contacted record due for its next touch today?

    Returns the next-touch spec when due, else None. Records with no
    `Next followup` set are never due — the sequence only schedules forward
    from a logged touch.
    """
    today = today or date.today()
    attempt = coerce_attempt(record.get("outreach_attempt"))
    if attempt >= MAX_ATTEMPTS:
        return None
    raw_due = (record.get("next_follow_up") or "").strip()
    if not raw_due:
        return None
    try:
        due = date.fromisoformat(raw_due[:10])
    except ValueError:
        return None
    if due > today:
        return None
    return next_touch(attempt)


def touches_logged_today(records, today=None):
    """Count records with an outreach touch logged on `today`.

    Both first contacts and follow-up touches write `message_sent_date`, so
    one predicate covers the whole daily workload: a record counts once per
    day no matter which touch it was. Only records still in an active
    outreach queue (Ready to Contact / Contacted) count — Won/Lost/
    Disqualified records are out of the sequence.
    """
    today = today or date.today()
    today_s = today.isoformat() if isinstance(today, date) else str(today)[:10]
    count = 0
    for r in records or []:
        if (r.get("current_queue") or "") not in {"Ready to Contact", "Contacted"}:
            continue
        val = (r.get("message_sent_date") or r.get("date_contacted") or "")[:10]
        if val and val >= today_s:
            count += 1
    return count
