"""Wake the research batch once a day, when the Render cron fires.

Render's clock is UTC. The cron schedule is 0 13 * * *, which is 7:00 AM
Central in winter (CST) and 8:00 AM Central in summer (CDT). As a guard
(the live cron may still be hourly), the script calls the API only when
the America/Chicago hour is 7 or the UTC hour is 13. Any other time it
exits 0 without spending anything. A restart of the website cannot start a
second run: the website no longer has its own timer.

Nothing in this file calls Perplexity or OpenAI. It only asks the API.
The API researches leads that are missing a phone and an email and have
fewer than two recorded enrichment attempts. The second attempt uses a
different method than the first (assessor records, or the web and
business-registry search). It caps the day at
ENRICHMENT_DAILY_CAP (default 10), does not retry a failed paid call
inside that run, and does not research a lead again inside
ENRICHMENT_RECHECK_DAYS. A lead is dropped for no contact only after
two attempts are on the record and both failed. Exterior-only permits
are out of lane and are not researched.
"""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

CHICAGO = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")
MORNING_HOUR = 7
CRON_UTC_HOUR = 13


def should_run(now: datetime) -> bool:
    """True at 7am Chicago or 13:00 UTC, so an hourly cron cannot overspend."""
    local = now.astimezone(CHICAGO) if now.tzinfo else now.replace(tzinfo=CHICAGO)
    return local.hour == MORNING_HOUR or local.astimezone(UTC).hour == CRON_UTC_HOUR


def _require(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        print(f"morning research: {name} is not set. Nothing was called.", file=sys.stderr)
        raise SystemExit(1)
    return value


def trigger(now: datetime | None = None) -> int:
    """POST the locked research route, or exit 0 outside the run hour.

    Returns the HTTP status. Exits the process on a missing setting or a
    non-2xx response so Render can mark the run failed.
    """
    moment = now or datetime.now(CHICAGO)
    local = moment.astimezone(CHICAGO) if moment.tzinfo else moment.replace(tzinfo=CHICAGO)
    if not should_run(local):
        print(f"morning research: skipped at {local.isoformat()}, not 7am Chicago or 13:00 UTC.")
        return 0
    print(f"morning research: running at {local.isoformat()}.")

    base = _require("PUBLIC_BACKEND_URL").rstrip("/")
    password = _require("APP_PASSWORD")
    secret = _require("WEBHOOK_CRON_SECRET")
    url = f"{base}/api/enrichment/run"
    request = urllib.request.Request(
        url,
        data=b"",
        method="POST",
        headers={
            "X-App-Password": password,
            "X-Cron-Secret": secret,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            body = response.read(2000).decode("utf-8", "replace")
            print(f"morning research: HTTP {response.status} {body}")
            return response.status
    except urllib.error.HTTPError as exc:
        detail = exc.read(2000).decode("utf-8", "replace")
        print(f"morning research: HTTP {exc.code} {detail}", file=sys.stderr)
        raise SystemExit(1) from exc
    except urllib.error.URLError as exc:
        print(f"morning research: could not reach the API: {exc.reason}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    trigger()
