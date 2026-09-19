"""
Slack alerts for Band A opportunities.

Design principles:
- One-way Incoming Webhook only (no bot token, no OAuth, no permissions).
- Webhook URL is read from env var SLACK_BLOODHOUND_WEBHOOK_URL and NEVER
  logged, returned from any API, or exposed to the frontend.
- Notification-only. Never triggers outreach.
- Dedupe tracking lives in MongoDB collection `slack_band_a_alerts`. A given
  opportunity is alerted at most once unless its `lead_score` climbs by
  ALERT_SCORE_DELTA points or more after the prior alert.
- Absent webhook URL is not an error: the app stays fully functional and
  logs a single safe configuration warning at boot.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

log = logging.getLogger("bloodhound.slack")

_WEBHOOK_ENV = "SLACK_BLOODHOUND_WEBHOOK_URL"
_APP_URL_ENV = "PUBLIC_APP_URL"
_BAND_A = "A"
ALERT_SCORE_DELTA = 10.0  # min score increase to re-alert an already-alerted lead

_COLLECTION = "slack_band_a_alerts"
_WARNED_ABSENT = False  # ensures the "not configured" warning fires at most once


def _webhook_url() -> Optional[str]:
    """Read the webhook secret at call time so hot-swaps take effect."""
    url = (os.environ.get(_WEBHOOK_ENV) or "").strip()
    return url or None


def is_configured() -> bool:
    return _webhook_url() is not None


def _log_missing_config_once() -> None:
    global _WARNED_ABSENT
    if _WARNED_ABSENT:
        return
    _WARNED_ABSENT = True
    log.warning(
        "Slack alerts: %s is not set — Band A alerts will be skipped. "
        "Set the env var to enable notifications. App remains fully functional.",
        _WEBHOOK_ENV,
    )


def _dashboard_link(opp_id: str) -> str:
    base = (
        os.environ.get(_APP_URL_ENV)
        or os.environ.get("PUBLIC_BACKEND_URL")
        or ""
    ).rstrip("/")
    if not base:
        return f"/opportunities/{opp_id}"
    return f"{base}/opportunities/{opp_id}"


def _fmt_score(v: Any) -> str:
    if v is None or v == "":
        return "—"
    try:
        f = float(v)
        return f"{int(f)}" if f.is_integer() else f"{f:.1f}"
    except (TypeError, ValueError):
        return str(v)


def _location(opp: Dict[str, Any]) -> Optional[str]:
    for k in ("project_address", "address", "city"):
        v = opp.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _build_blocks(opp: Dict[str, Any], *, reason: str) -> List[Dict[str, Any]]:
    """Slack Block Kit payload — sentence-case, no emoji-heavy noise."""
    name = opp.get("name") or opp.get("opportunity_id") or "Untitled opportunity"
    lane_label = opp.get("lane_label") or opp.get("lane") or "—"
    source = opp.get("source") or "—"
    score = _fmt_score(opp.get("priority_score"))
    conf = _fmt_score(opp.get("confidence_score") or opp.get("evidence_confidence"))
    why = opp.get("recommendation_reason") or opp.get("evidence_summary") or "—"
    # `recommended_action` first — Airtable's "Next action" was deprecated
    # 2026-02-19 and its DTO key (`next_best_action`) is now derived from
    # `recommended_action` upstream, so both should be equivalent. Keep the
    # secondary read as a defensive fallback for records still in flight.
    next_action = opp.get("recommended_action") or opp.get("next_best_action") or "—"
    location = _location(opp)
    link = _dashboard_link(opp.get("id") or opp.get("opportunity_id") or "")

    header = (
        "Band A — new opportunity"
        if reason == "new"
        else "Band A — score up"
    )

    fields = [
        {"type": "mrkdwn", "text": f"*Lead score*\n{score} / 100"},
        {"type": "mrkdwn", "text": f"*Confidence*\n{conf}"},
        {"type": "mrkdwn", "text": f"*Lane*\n{lane_label}"},
        {"type": "mrkdwn", "text": f"*Source*\n{source}"},
    ]
    if location:
        fields.append({"type": "mrkdwn", "text": f"*Location*\n{location}"})

    blocks: List[Dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": header}},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{name}*"},
        },
        {"type": "section", "fields": fields},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Why it matters*\n{why}"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Next best action*\n{next_action}"},
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Open in Bloodhound"},
                    "url": link,
                    "style": "primary",
                }
            ],
        },
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "Notification only · no outreach triggered"}]},
    ]
    return blocks


class SlackAlerter:
    """Async dispatcher + Mongo-backed dedupe."""

    def __init__(self, mongo_url: str, db_name: str):
        self._client = AsyncIOMotorClient(mongo_url)
        self._db = self._client[db_name]
        self._col = self._db[_COLLECTION]

    async def _prior(self, opp_id: str) -> Optional[Dict[str, Any]]:
        return await self._col.find_one({"opportunity_id": opp_id})

    async def _persist(self, opp_id: str, score: Optional[float], reason: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._col.update_one(
            {"opportunity_id": opp_id},
            {
                "$set": {
                    "opportunity_id": opp_id,
                    "last_alerted_score": score,
                    "alert_sent_at": now,
                    "last_reason": reason,
                },
                "$inc": {"alert_count": 1},
            },
            upsert=True,
        )

    def _reason(self, opp: Dict[str, Any], prior: Optional[Dict[str, Any]]) -> Optional[str]:
        """Return 'new', 'promoted', or None if no alert should fire."""
        band = opp.get("priority_band")
        if band != _BAND_A:
            return None
        score = opp.get("priority_score")
        try:
            score_f = float(score) if score is not None else None
        except (TypeError, ValueError):
            score_f = None
        if prior is None:
            return "new"
        prev = prior.get("last_alerted_score")
        try:
            prev_f = float(prev) if prev is not None else None
        except (TypeError, ValueError):
            prev_f = None
        if score_f is None or prev_f is None:
            return None
        if score_f - prev_f >= ALERT_SCORE_DELTA:
            return "promoted"
        return None

    async def _post(self, blocks: List[Dict[str, Any]], fallback_text: str) -> bool:
        url = _webhook_url()
        if not url:
            return False
        payload = {"text": fallback_text, "blocks": blocks}
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.post(url, json=payload)
            if r.status_code >= 300:
                # Slack returns 200 "ok" on success. Never log body verbatim in
                # case it echoes anything sensitive; log status only.
                log.warning("Slack alert non-2xx status=%s", r.status_code)
                return False
            return True
        except Exception:
            log.exception("Slack alert POST failed")
            return False

    async def evaluate_and_alert(self, opportunities: List[Dict[str, Any]]) -> int:
        """Scan opportunities and dispatch alerts for anything that qualifies.
        Returns the number of alerts actually sent."""
        if not is_configured():
            _log_missing_config_once()
            return 0
        sent = 0
        for opp in opportunities:
            opp_id = opp.get("id") or opp.get("opportunity_id")
            if not opp_id:
                continue
            try:
                prior = await self._prior(opp_id)
                reason = self._reason(opp, prior)
                if not reason:
                    continue
                blocks = _build_blocks(opp, reason=reason)
                fallback = (
                    f"Band A opportunity — {opp.get('name') or opp_id} "
                    f"(score {_fmt_score(opp.get('priority_score'))})"
                )
                ok = await self._post(blocks, fallback)
                if ok:
                    await self._persist(opp_id, opp.get("priority_score"), reason)
                    sent += 1
            except Exception:
                log.exception("Slack alert evaluation failed for %s", opp_id)
        if sent:
            log.info("Slack alerts dispatched: %d Band A notifications", sent)
        return sent


_singleton: Optional[SlackAlerter] = None


def get_slack_alerter() -> Optional[SlackAlerter]:
    global _singleton
    if _singleton is not None:
        return _singleton
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not (mongo_url and db_name):
        log.warning("Slack alerter: MONGO_URL/DB_NAME missing — dedupe unavailable, alerts disabled")
        return None
    _singleton = SlackAlerter(mongo_url, db_name)
    if not is_configured():
        _log_missing_config_once()
    return _singleton
