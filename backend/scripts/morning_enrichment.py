"""Wake the research batch once, at 7am in New Orleans.

Render's clock is UTC and does not follow daylight saving time. This
script is scheduled every hour and does nothing unless the local hour
in America/Chicago is 7. A restart of the website cannot start a second
run: the website no longer has its own timer.

Nothing in this file calls Perplexity or OpenAI. It only asks the API,
which already caps the day at ENRICHMENT_DAILY_CAP (default 10) and
does not retry a failed paid call.
"""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

CHICAGO = ZoneInfo("America/Chicago")
MORNING_HOUR = 7


def should_run(now: datetime) -> bool:
    """True during the 7 o'clock hour in Chicago, standard or daylight time."""
    local = now.astimezone(CHICAGO) if now.tzinfo else now.replace(tzinfo=CHICAGO)
    return local.hour == MORNING_HOUR


def _require(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        print(f"morning research: {name} is not set. Nothing was called.", file=sys.stderr)
        raise SystemExit(1)
    return value


def trigger(now: datetime | None = None) -> int:
    """POST the locked research route, or exit 0 outside the morning hour.

    Returns the HTTP status. Exits the process on a missing setting or a
    non-2xx response so Render can mark the run failed.
    """
    moment = now or datetime.now(CHICAGO)
    if not should_run(moment):
        local = moment.astimezone(CHICAGO)
        print(f"morning research: skipped, Chicago hour is {local.hour}, not {MORNING_HOUR}.")
        return 0

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
