"""
One place to build pyairtable clients.

Without a timeout, a single stalled Airtable response blocks its worker
forever (requests' default read timeout is None). On 2026-10-03 that froze
the whole backend: every request queued behind it and the app stopped
loading. Every Airtable client in the backend goes through make_api().
"""
from __future__ import annotations

from pyairtable import Api

# (connect, read) seconds. Airtable list pages normally return in < 2s;
# pyairtable's default retry strategy still retries 429/5xx.
AIRTABLE_TIMEOUT = (5, 20)


def make_api(api_key: str) -> Api:
    return Api(api_key, timeout=AIRTABLE_TIMEOUT)
