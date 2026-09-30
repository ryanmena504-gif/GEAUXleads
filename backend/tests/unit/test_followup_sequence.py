"""Four-touch outreach sequence.

Guards the shape Ryan asked for: touch 1 = email (next due in 3 days),
touch 2 = call + text (next due day 7), touch 3 = follow-up email (next due
day 14), touch 4 = breakup (sequence closes, lead becomes Lost). No fifth
touch is ever scheduled.
"""
from datetime import date, timedelta

import pytest

from services.followup_sequence import (
    MAX_ATTEMPTS,
    advance,
    coerce_attempt,
    due_for_touch,
    next_touch,
)


def test_max_attempts_is_four():
    assert MAX_ATTEMPTS == 4


# ------------------------------------------------------- next_touch
def test_first_touch_is_email():
    t = next_touch(0)
    assert t["attempt"] == 1 and t["of"] == 4
    assert t["label"] == "Email" and t["channel"] == "Email"


def test_second_touch_is_call_and_text():
    t = next_touch(1)
    assert t["attempt"] == 2
    assert t["label"] == "Call + text" and t["channel"] == "Call"


def test_third_touch_is_follow_up_email():
    t = next_touch(2)
    assert t["attempt"] == 3 and t["label"] == "Follow-up email"


def test_fourth_touch_is_breakup():
    t = next_touch(3)
    assert t["attempt"] == 4 and t["label"] == "Breakup email"


def test_no_fifth_touch():
    assert next_touch(4) is None
    assert next_touch(99) is None


# ---------------------------------------------------------- advance
def test_advance_first_touch_schedules_day_three():
    today = date(2026, 9, 30)
    r = advance(0, today)
    assert r["outreach_attempt"] == 1
    assert r["next_follow_up"] == "2026-10-03"
    assert r["closes_lead"] is False
    assert r["next"]["attempt"] == 2


def test_advance_second_touch_schedules_four_days_out():
    today = date(2026, 9, 30)
    r = advance(1, today)
    assert r["outreach_attempt"] == 2
    assert r["next_follow_up"] == "2026-10-04"


def test_advance_third_touch_schedules_seven_days_out():
    today = date(2026, 9, 30)
    r = advance(2, today)
    assert r["outreach_attempt"] == 3
    assert r["next_follow_up"] == "2026-10-07"


def test_advance_fourth_touch_closes_lead():
    today = date(2026, 9, 30)
    r = advance(3, today)
    assert r["outreach_attempt"] == 4
    assert r["next_follow_up"] is None
    assert r["closes_lead"] is True
    assert r["next"] is None


def test_advance_past_four_raises():
    with pytest.raises(ValueError):
        advance(4)


# ---------------------------------------------------- coerce_attempt
@pytest.mark.parametrize("raw,expected", [
    (None, 0), ("", 0), ("garbage", 0), ([], 0),
    (0, 0), (2, 2), ("3", 3), (2.9, 2),
    (99, 4), (-5, 0),
])
def test_coerce_attempt_clamps(raw, expected):
    assert coerce_attempt(raw) == expected


# ------------------------------------------------------ due_for_touch
def _rec(attempt, next_follow_up):
    return {
        "outreach_attempt": attempt,
        "next_follow_up": next_follow_up,
        "current_queue": "Contacted",
    }


def test_due_when_followup_date_is_today_or_earlier():
    today = date(2026, 9, 30)
    assert due_for_touch(_rec(1, "2026-09-30"), today)["attempt"] == 2
    assert due_for_touch(_rec(1, "2026-09-29"), today)["attempt"] == 2


def test_not_due_when_followup_is_in_future():
    today = date(2026, 9, 30)
    assert due_for_touch(_rec(1, "2026-10-01"), today) is None


def test_not_due_when_sequence_complete():
    today = date(2026, 9, 30)
    assert due_for_touch(_rec(4, "2026-09-01"), today) is None


def test_not_due_when_no_followup_scheduled():
    today = date(2026, 9, 30)
    assert due_for_touch(_rec(0, ""), today) is None
    assert due_for_touch(_rec(0, None), today) is None


def test_not_due_on_garbage_date():
    today = date(2026, 9, 30)
    assert due_for_touch(_rec(1, "not-a-date"), today) is None


def test_due_touch_carries_channel_and_label():
    today = date(2026, 9, 30)
    t = due_for_touch(_rec(1, "2026-09-30"), today)
    assert t == {"attempt": 2, "of": 4, "label": "Call + text", "channel": "Call"}
    # datetime-flavoured Airtable values (with time component) still parse
    t = due_for_touch(_rec(2, "2026-09-30T00:00:00.000Z"), today)
    assert t["attempt"] == 3


# --------------------------------- daily quota counts follow-up touches
def _quota_records():
    # A first contact sent today, a follow-up touch logged today, one
    # untouched candidate, one stale send, and one Lost record touched today
    # (closed records are out of the sequence and must not count).
    return [
        {"id": "rec1", "current_queue": "Contacted", "message_sent_date": "2026-09-30T14:00:00+00:00"},
        {"id": "rec2", "current_queue": "Ready to Contact", "message_sent_date": "2026-09-30T15:00:00+00:00"},
        {"id": "rec3", "current_queue": "Ready to Contact", "message_sent_date": ""},
        {"id": "rec4", "current_queue": "Contacted", "message_sent_date": "2026-09-20T14:00:00+00:00"},
        {"id": "rec5", "current_queue": "All Projects", "message_sent_date": "2026-09-30T16:00:00+00:00"},
    ]


def test_touches_logged_today_counts_first_contacts_and_followups():
    from services.followup_sequence import touches_logged_today

    assert touches_logged_today(_quota_records(), date(2026, 9, 30)) == 2


def test_touches_logged_today_ignores_closed_queues_and_stale_dates():
    from services.followup_sequence import touches_logged_today

    assert touches_logged_today(_quota_records(), date(2026, 10, 1)) == 0
    assert touches_logged_today([], date(2026, 9, 30)) == 0
