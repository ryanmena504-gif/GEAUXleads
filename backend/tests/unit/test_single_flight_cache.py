"""Concurrent reads must trigger ONE Airtable download, not one per request.

Parallel full-table downloads tripped Airtable's 5 req/s limit (30 s lockout)
and froze production on 2026-10-03.
"""
from __future__ import annotations

import threading
import time

from services.discovery_service import DiscoveryReader as Reader


class SlowTable:
    def __init__(self):
        self.calls = 0
        self._lock = threading.Lock()

    def all(self):
        with self._lock:
            self.calls += 1
        time.sleep(0.2)
        return [{"id": "rec1", "createdTime": "2026-10-01T00:00:00Z", "fields": {"Name": "A"}}]


def _hammer(fn, n=8):
    out = []
    threads = [threading.Thread(target=lambda: out.append(fn())) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out


def test_discovery_reader_downloads_once_under_concurrency():
    r = Reader.__new__(Reader)
    r._table = SlowTable()
    r._table_name = "Landlords"
    r._cache_ttl = 60.0
    r._lock = threading.Lock()
    r._refresh_lock = threading.Lock()
    r._cache = []
    r._last_refresh = 0.0
    r._last_error = None
    results = _hammer(r.all)
    assert r._table.calls == 1
    assert all(len(x) == 1 for x in results)       # cold callers waited, got data


def test_opportunity_cache_refreshes_once_under_concurrency():
    from services.airtable_service import AirtableOpportunityService as Svc
    svc = Svc.__new__(Svc)
    svc._table = SlowTable()
    svc._cache_ttl = 60.0
    svc._lock = threading.Lock()
    svc._refresh_gate = threading.Lock()
    svc._cache = {}
    svc._last_refresh = 0.0
    svc._refresh_started = 0.0
    svc._refreshing = False
    svc._consecutive_failures = 0
    svc._last_error = None
    svc._last_error_ts = 0.0
    svc._duplicate_index = {}
    svc._record_to_opportunity = lambda r: {"id": r["id"], "name": "A"}

    class _Ingest:
        def start(self): pass
        def record_seen(self): pass
        def record_failure(self, *a): pass
        def record_projected(self): pass
        def finish(self): pass

    svc._ingestion = _Ingest()
    _hammer(svc._refresh_cache)
    assert svc._table.calls == 1
