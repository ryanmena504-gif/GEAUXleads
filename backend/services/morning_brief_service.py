"""
Morning Brief composer.

Assembles Ryan's daily 7am morning-brief content. Zero writes — this service
never mutates opportunities, Airtable, or any store. Reads the opportunity
list + handoff log through the existing services and returns a plain dict
the API layer serializes as JSON (for the in-app panel) and the email
renderer converts to HTML (for the scheduled 7am send).

Sections:
  • Follow-ups due — leads Ryan touched but never nudged, from the same
    logic as /api/follow-ups/due (estimate_check → text_nudge → email_nudge).
  • New Ready today — records the classifier promoted to `Current Queue =
    "Ready to Contact"` in the last 24 hours.
  • Estimate deadlines — records with outreach_status in {Estimate
    requested, Estimate sent} whose last reply is ≥ 7 days ago.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any, Dict, List, Optional

log = logging.getLogger("bloodhound.morning_brief")

# Reuse the follow-ups bucket vocabulary from server.py so operator sees the
# same buckets both places.
FOLLOWUP_LABEL = {
    "estimate_check": "Estimate check",
    "text_nudge": "Text nudge",
    "email_nudge": "Email nudge",
}
NEW_READY_WINDOW_HOURS = 24
ESTIMATE_STALE_DAYS = 7

# Turnover check-in cadences (in days) — how often we nudge landlords per
# their governed `Turnover Cadence` value. Landlords with no cadence set
# default to Quarterly so they still surface eventually.
TURNOVER_CADENCE_DAYS = {
    "Monthly": 30,
    "Quarterly": 60,
    "Annual": 180,
    "Unknown": 90,
}
DEFAULT_TURNOVER_DAYS = 60


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _hours_since(value: Optional[str], now: datetime) -> Optional[float]:
    parsed = _parse_iso(value)
    if not parsed:
        return None
    return (now - parsed).total_seconds() / 3600.0


def _first(*values: Any) -> Any:
    for v in values:
        if v:
            return v
    return None


async def compose_brief(
    *,
    opportunity_service: Any,
    handoff_service: Optional[Any],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Assemble the brief. Never raises — returns a stable envelope even when
    a downstream service is unavailable (empty section instead of a 500)."""
    now = now or datetime.now(timezone.utc)
    try:
        all_ops = opportunity_service.all() if hasattr(opportunity_service, "all") else []
    except Exception:
        log.exception("Morning brief: opportunity list unavailable")
        all_ops = []

    ready_new = _pick_new_ready(all_ops, now)
    estimate_nudges = _pick_estimate_deadlines(all_ops, now)
    follow_ups = await _pick_follow_ups(all_ops, handoff_service, now)
    turnover_checkins = _pick_turnover_checkins(all_ops, now)

    total = (
        len(ready_new)
        + len(estimate_nudges)
        + len(follow_ups)
        + len(turnover_checkins)
    )
    return {
        "generated_at": now.isoformat(),
        "operator_name": "Ryan",
        "counts": {
            "new_ready": len(ready_new),
            "follow_ups": len(follow_ups),
            "estimate_nudges": len(estimate_nudges),
            "turnover_checkins": len(turnover_checkins),
            "total": total,
        },
        "new_ready": ready_new,
        "follow_ups": follow_ups,
        "estimate_nudges": estimate_nudges,
        "turnover_checkins": turnover_checkins,
    }


def _pick_new_ready(all_ops: List[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for o in all_ops:
        if (o.get("current_queue") or "").strip() != "Ready to Contact":
            continue
        stamp = _first(o.get("last_classified_at"), o.get("created_time"))
        hours = _hours_since(stamp, now)
        if hours is None or hours > NEW_READY_WINDOW_HOURS:
            continue
        out.append(_row(o, {"hours_since_ready": round(hours, 1)}))
    out.sort(key=lambda r: -(r.get("governed_priority_score") or 0))
    return out[:5]


def _pick_estimate_deadlines(all_ops: List[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for o in all_ops:
        status = (o.get("outreach_status") or "").strip()
        if status not in {"Estimate requested", "Estimate sent"}:
            continue
        last_touch = _first(o.get("date_replied"), o.get("date_contacted"), o.get("message_sent_date"))
        hours = _hours_since(last_touch, now)
        if hours is None:
            continue
        days = hours / 24.0
        if days < ESTIMATE_STALE_DAYS:
            continue
        out.append(_row(o, {"days_since_reply": round(days, 1)}))
    out.sort(key=lambda r: -(r.get("days_since_reply") or 0))
    return out[:5]


def _pick_turnover_checkins(all_ops: List[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    """Landlords whose next turnover-check date has passed.

    A landlord shows up here when:
      • lane == "landlord"
      • current_queue is "Contacted" or "Ready to Contact" (not All Projects)
      • the days since their last touch exceeds their governed Turnover
        Cadence window (Monthly=30, Quarterly=60, Annual=180, else 60).

    Read-only. Never invents a cadence — falls back to 60 days if unset so
    landlords still surface eventually.
    """
    out: List[Dict[str, Any]] = []
    for o in all_ops:
        if (o.get("lane") or "").lower() != "landlord":
            continue
        queue = (o.get("current_queue") or "").strip()
        if queue not in {"Contacted", "Ready to Contact"}:
            continue
        cadence = (o.get("turnover_cadence") or "").strip()
        window_days = TURNOVER_CADENCE_DAYS.get(cadence, DEFAULT_TURNOVER_DAYS)
        last_touch = _first(
            o.get("last_turnover_check"),
            o.get("date_contacted"),
            o.get("message_sent_date"),
        )
        hours = _hours_since(last_touch, now)
        # If we've never touched them and they're already Ready, surface now.
        days = (hours / 24.0) if hours is not None else float("inf")
        if days < window_days:
            continue
        out.append(_row(o, {
            "cadence": cadence or "Unknown",
            "cadence_days": window_days,
            "days_since_touch": None if hours is None else round(days, 1),
            "portfolio_size": o.get("portfolio_size"),
        }))
    # Longest-overdue first, then highest score.
    out.sort(key=lambda r: (
        -(r.get("days_since_touch") or 9999),
        -(r.get("governed_priority_score") or 0),
    ))
    return out[:5]


async def _pick_follow_ups(
    all_ops: List[Dict[str, Any]],
    handoff_service: Optional[Any],
    now: datetime,
) -> List[Dict[str, Any]]:
    if not handoff_service:
        return []
    try:
        handoffs = await handoff_service.list_recent(limit=500)
    except Exception:
        log.exception("Morning brief: handoff service unavailable")
        return []

    last_by_opp: Dict[str, Dict[str, Any]] = {}
    for h in handoffs:
        opp_id = h.get("opportunity_id")
        if not opp_id or opp_id in last_by_opp:
            continue
        last_by_opp[opp_id] = h

    if not last_by_opp:
        return []

    by_id = {o.get("id"): o for o in all_ops if o.get("id")}
    ACTIVE_CLOSED = {"Won", "Lost", "Disqualified"}
    ESTIMATE_STATUSES = {"Estimate requested", "Estimate sent"}
    out: List[Dict[str, Any]] = []

    for opp_id, h in last_by_opp.items():
        opp = by_id.get(opp_id)
        if not opp:
            continue
        if (opp.get("status") or "").strip() in ACTIVE_CLOSED:
            continue
        hours = _hours_since(h.get("at"), now)
        if hours is None:
            continue
        days = hours / 24.0
        channel = (h.get("channel") or "").lower()
        status = (opp.get("status") or "").strip()
        bucket = None
        if status in ESTIMATE_STATUSES and days >= 7:
            bucket = "estimate_check"
        elif channel == "email" and days >= 5:
            bucket = "email_nudge"
        elif channel == "text" and days >= 3:
            bucket = "text_nudge"
        if not bucket:
            continue
        row = _row(opp, {
            "bucket": bucket,
            "bucket_label": FOLLOWUP_LABEL.get(bucket, bucket),
            "days_since_touch": round(days, 1),
            "last_channel": channel or "unknown",
        })
        out.append(row)

    # Same ordering as /api/follow-ups/due for consistency.
    BUCKET_ORDER = {"estimate_check": 0, "text_nudge": 1, "email_nudge": 2}
    out.sort(key=lambda r: (
        BUCKET_ORDER.get(r.get("bucket"), 99),
        -(r.get("governed_priority_score") or 0),
        -(r.get("days_since_touch") or 0),
    ))
    return out[:5]


def _row(opp: Dict[str, Any], extras: Dict[str, Any]) -> Dict[str, Any]:
    base = {
        "id": opp.get("id"),
        "name": opp.get("name"),
        "project_type": opp.get("project_type"),
        "project_address": opp.get("project_address"),
        "current_queue": opp.get("current_queue"),
        "contact_readiness": opp.get("contact_readiness"),
        "contact_state": opp.get("contact_state"),
        "governed_priority_score": opp.get("governed_priority_score"),
        "money_signal": opp.get("money_signal"),
        "premium_fit": opp.get("premium_fit"),
        "estimated_value": opp.get("estimated_value"),
        "current_recommendation": opp.get("current_recommendation"),
    }
    base.update(extras)
    return base


# ---- HTML rendering ---------------------------------------------------------

def _fmt_money(value: Any) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "—"
    if n >= 1_000:
        return f"${n / 1000:.0f}K"
    return f"${n:.0f}"


def _row_html(row: Dict[str, Any], app_base_url: str, note: str) -> str:
    name = escape(row.get("name") or "Untitled opportunity")
    ptype = escape(row.get("project_type") or "")
    score = row.get("governed_priority_score")
    money = _fmt_money(row.get("estimated_value"))
    reco = escape(row.get("current_recommendation") or "")
    opp_id = escape(row.get("id") or "")
    link = f"{app_base_url}/opportunities/{opp_id}"
    score_label = escape(str(score) if score is not None else "—")
    reco_block = (
        f'<div style="font-size:12.5px;color:#8a6a2b;margin-top:4px">{reco}</div>'
        if reco else ""
    )
    return (
        f'<tr><td style="padding:12px 0;border-bottom:1px solid #e5e2d8">'
        f'  <div style="font-size:15px;font-weight:600;color:#2b2b2b">'
        f'    <a href="{escape(link)}" style="color:#8a6a2b;text-decoration:none">{name}</a>'
        f'  </div>'
        f'  <div style="font-size:12px;color:#8a8578;margin-top:2px">'
        f'    {ptype} · {money} · Score {score_label}'
        f'  </div>'
        f'  <div style="font-size:12px;color:#5a5a5a;margin-top:6px">{escape(note)}</div>'
        f'  {reco_block}'
        f'</td></tr>'
    )


def _section_html(title: str, rows_html: str, empty_text: str) -> str:
    empty_row = (
        '<tr><td style="padding:12px 0;font-size:13px;color:#8a8578">'
        f'{escape(empty_text)}'
        '</td></tr>'
    )
    body = rows_html if rows_html else empty_row
    return (
        f'<div style="margin-top:24px">'
        f'  <div style="font-family:Arial,sans-serif;font-size:11px;letter-spacing:1.5px;'
        f'text-transform:uppercase;color:#8a6a2b;font-weight:600;margin-bottom:6px">{escape(title)}</div>'
        f'  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="font-family:Arial,sans-serif">'
        f'    {body}'
        f'  </table>'
        f'</div>'
    )


def render_brief_html(brief: Dict[str, Any], app_base_url: str) -> str:
    """Render the brief dict as an inline-styled HTML email body."""
    counts = brief.get("counts", {})
    generated = brief.get("generated_at") or ""
    try:
        date_label = datetime.fromisoformat(generated.replace("Z", "+00:00")).strftime("%A, %B %d")
    except Exception:
        date_label = "This morning"

    ready_rows = "".join(
        _row_html(r, app_base_url, f'Promoted to Ready {r.get("hours_since_ready", "?")}h ago')
        for r in brief.get("new_ready", [])
    )
    followup_rows = "".join(
        _row_html(r, app_base_url,
                  f'{r.get("bucket_label", "Follow-up")} · {r.get("days_since_touch", "?")} days since last {r.get("last_channel", "touch")}')
        for r in brief.get("follow_ups", [])
    )
    estimate_rows = "".join(
        _row_html(r, app_base_url, f'Estimate sent {r.get("days_since_reply", "?")} days ago')
        for r in brief.get("estimate_nudges", [])
    )
    def _fmt_turnover_note(r: Dict[str, Any]) -> str:
        cadence = r.get("cadence") or "cadence unknown"
        d = r.get("days_since_touch")
        since = "never nudged" if d is None else f"{d} days since last touch"
        return f"Turnover check-in · {cadence} cadence · {since}"

    turnover_rows = "".join(
        _row_html(r, app_base_url, _fmt_turnover_note(r))
        for r in brief.get("turnover_checkins", [])
    )

    ready_section = _section_html(
        f'New Ready to Contact ({counts.get("new_ready", 0)})',
        ready_rows,
        "Nothing newly promoted in the last 24 hours.",
    )
    followup_section = _section_html(
        f'Follow-ups due ({counts.get("follow_ups", 0)})',
        followup_rows,
        "No follow-ups are overdue today.",
    )
    estimate_section = _section_html(
        f'Estimate deadlines ({counts.get("estimate_nudges", 0)})',
        estimate_rows,
        "No estimates have gone quiet.",
    )
    turnover_section = _section_html(
        f'Turnover check-ins ({counts.get("turnover_checkins", 0)})',
        turnover_rows,
        "No landlord check-ins are due.",
    ) if counts.get("turnover_checkins", 0) > 0 else ""

    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:#fbf8f0;padding:32px 0;font-family:Arial,sans-serif">'
        f'  <tr><td align="center">'
        f'    <table role="presentation" width="560" cellpadding="0" cellspacing="0" '
        f'style="background:#ffffff;border:1px solid #e5e2d8;border-radius:8px;padding:32px">'
        f'      <tr><td>'
        f'        <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;'
        f'color:#8a6a2b;font-weight:600">Bloodhound · Morning brief</div>'
        f'        <h1 style="margin:8px 0 0 0;font-size:22px;color:#2b2b2b;font-weight:700">'
        f'          Good morning, Ryan.'
        f'        </h1>'
        f'        <div style="margin-top:4px;font-size:13px;color:#8a8578">{escape(date_label)}</div>'
        f'        <div style="margin-top:16px;font-size:13.5px;line-height:1.55;color:#3a3a3a">'
        f'          {counts.get("total", 0)} things want your attention this morning. '
        f'          Everything below is a native draft — nothing sends until you press Send yourself.'
        f'        </div>'
        f'        {ready_section}'
        f'        {followup_section}'
        f'        {turnover_section}'
        f'        {estimate_section}'
        f'        <div style="margin-top:28px;padding-top:16px;border-top:1px solid #e5e2d8;'
        f'font-size:11px;color:#8a8578;line-height:1.6">'
        f'          Sent by Bloodhound — your governed queue for The Shirtless Handyman. '
        f'          You are receiving this because morning-brief delivery is enabled in Settings.'
        f'        </div>'
        f'      </td></tr>'
        f'    </table>'
        f'  </td></tr>'
        f'</table>'
    )
