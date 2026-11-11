"""Concurrent reads must trigger ONE Airtable download, not one per request.

Parallel full-table downloads tripped Airtable's 5 req/s limit (30 s lockout)
and froze production on 2026-10-03. The dashboard reader and the leads reader
used to keep separate guards, so one cold page still downloaded Leads twice.
"""
from __future__ import annotations

import asyncio
import threading
import time

from services.airtable_lists import _slot, key_for, reset_for_tests
from services.discovery_service import DiscoveryReader as Reader


class SlowTable:
    def __init__(self, counter=None, started=None, release=None):
        self.calls = 0
        self._lock = threading.Lock()
        self._counter = counter
        self._started = started
        self._release = release

    def all(self, **_kwargs):
        with self._lock:
            self.calls += 1
            if self._counter is not None:
                self._counter["calls"] += 1
        if self._started is not None:
            self._started.set()
        if self._release is not None:
            self._release.wait(timeout=2)
        else:
            time.sleep(0.2)
        return [{
            "id": "rec1",
            "createdTime": "2026-10-01T00:00:00Z",
            "fields": {
                "Name": "A",
                "Default Draft": "Hello",
                "Status": "Active",
                "Key": "daily_outreach_target",
                "Value": "5",
            },
        }]


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


def test_leads_cache_refreshes_once_under_concurrency():
    from services.leads_service import LeadsAirtableService as Svc
    svc = Svc.__new__(Svc)
    svc._table = SlowTable()
    svc._cache_ttl = 60.0
    svc._lock = threading.Lock()
    svc._refresh_gate = threading.Lock()
    svc._cache = {}
    svc._last_refresh = 0.0
    svc._duplicate_index = {}
    svc._record_to_dto = lambda r: {"id": r["id"], "name": "A"}
    _hammer(svc._refresh_cache)
    assert svc._table.calls == 1


def _opportunity(table, base="appSHARE", table_id="tblLeads"):
    from services.airtable_service import AirtableOpportunityService as Svc
    svc = Svc.__new__(Svc)
    svc._table = table
    svc._base_id = base
    svc._table_id = table_id
    svc._table_name = "Leads"
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
        def start(self):
            pass

        def record_seen(self):
            pass

        def record_failure(self, *a):
            pass

        def record_projected(self):
            pass

        def finish(self):
            pass

    svc._ingestion = _Ingest()
    return svc


def _leads(table, base="appSHARE", table_id="tblLeads"):
    from services.leads_service import LeadsAirtableService as Svc
    svc = Svc.__new__(Svc)
    svc._table = table
    svc._base_id = base
    svc._table_id = table_id
    svc._table_name = "Leads"
    svc._cache_ttl = 60.0
    svc._lock = threading.Lock()
    svc._refresh_gate = threading.Lock()
    svc._cache = {}
    svc._last_refresh = 0.0
    svc._duplicate_index = {}
    svc._record_to_dto = lambda r: {"id": r["id"], "name": "A"}
    return svc


def test_dashboard_and_leads_readers_share_one_download():
    """Dashboard and next-best-action must share one Leads download.

    Separate table objects prove the share is by base and table id, not by
    which Python wrapper happens to make the request.
    """
    reset_for_tests()
    counter = {"calls": 0}
    started = threading.Event()
    release = threading.Event()
    dashboard = _opportunity(SlowTable(counter, started, release))
    leads = _leads(SlowTable(counter, started, release))
    threads = [
        threading.Thread(target=dashboard._refresh_cache),
        threading.Thread(target=leads._refresh_cache),
        threading.Thread(target=dashboard._refresh_cache),
        threading.Thread(target=leads._refresh_cache),
    ]
    for thread in threads:
        thread.start()
    assert started.wait(2), "no reader started a download"
    key = key_for("appSHARE", "tblLeads", "Leads", dashboard._table)
    slot = _slot(key)

    def second_reader_is_waiting():
        with slot.cv:
            return slot.inflight and slot.waiters >= 1

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and not second_reader_is_waiting():
        time.sleep(0.01)
    assert second_reader_is_waiting(), "the other reader started its own download"
    assert counter["calls"] == 1
    release.set()
    for thread in threads:
        thread.join()
    assert counter["calls"] == 1
    assert len(dashboard._cache) == 1
    assert len(leads._cache) == 1


def test_second_reader_reuses_a_fresh_download():
    """Health/deep loads the dashboard, then the leads list. That is one list."""
    reset_for_tests()
    counter = {"calls": 0}
    dashboard = _opportunity(SlowTable(counter))
    leads = _leads(SlowTable(counter))
    dashboard._refresh_cache()
    leads._refresh_cache()
    assert counter["calls"] == 1
    assert len(leads._cache) == 1


def test_force_refresh_still_downloads():
    reset_for_tests()
    counter = {"calls": 0}
    dashboard = _opportunity(SlowTable(counter))
    leads = _leads(SlowTable(counter))
    dashboard._refresh_cache()
    leads._refresh_cache(force=True)
    assert counter["calls"] == 2


def test_different_tables_do_not_list_in_parallel():
    """Playbooks, discovery, raw signals, and settings share the one list lock."""
    reset_for_tests()
    overlap = {"n": 0, "max": 0, "lock": threading.Lock()}

    class Tracking(SlowTable):
        def all(self, **kwargs):
            with overlap["lock"]:
                overlap["n"] += 1
                overlap["max"] = max(overlap["max"], overlap["n"])
            try:
                return super().all(**kwargs)
            finally:
                with overlap["lock"]:
                    overlap["n"] -= 1

    from services.airtable_settings_service import AirtableSettingsService
    from services.playbook_service import PlaybookService
    from services.promotion_service import PromotionService

    discovery = Reader.__new__(Reader)
    discovery._table = Tracking()
    discovery._base_id = "appSHARE"
    discovery._table_name = "Landlords"
    discovery._cache_ttl = 60.0
    discovery._lock = threading.Lock()
    discovery._refresh_lock = threading.Lock()
    discovery._cache = []
    discovery._last_refresh = 0.0
    discovery._last_error = None

    playbooks = PlaybookService.__new__(PlaybookService)
    playbooks._table = Tracking()
    playbooks._base_id = "appSHARE"
    playbooks._table_name = "tblPlaybooks"
    playbooks._cache_ttl = 60.0
    playbooks._lock = threading.Lock()
    playbooks._cache = []
    playbooks._last_refresh = 0.0

    raw = PromotionService.__new__(PromotionService)
    raw._raw = Tracking()
    raw._base_id = "appSHARE"
    raw._table_name = "Raw Signals"
    raw._lock = threading.Lock()
    raw._cache = None
    raw._cached_at = 0.0

    settings = AirtableSettingsService.__new__(AirtableSettingsService)
    settings_table = Tracking()
    settings._table = lambda: settings_table
    settings._base_id = "appSHARE"
    settings._table_id = "tblSettings"
    settings._table_name = "App Settings"
    settings._ready = True
    settings._lock = threading.Lock()
    settings._cache = {}
    settings._cache_ts = 0.0

    threads = [
        threading.Thread(target=discovery.all),
        threading.Thread(target=playbooks.list),
        threading.Thread(target=raw.waiting),
        threading.Thread(target=settings._list_records),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert overlap["max"] == 1
    assert discovery._table.calls == 1
    assert playbooks._table.calls == 1
    assert raw._raw.calls == 1
    assert settings_table.calls == 1


def test_playbook_and_settings_readers_download_once_under_concurrency():
    """These two readers had no single-flight guard of their own."""
    reset_for_tests()
    from services.airtable_settings_service import AirtableSettingsService
    from services.playbook_service import PlaybookService

    playbooks = PlaybookService.__new__(PlaybookService)
    playbooks._table = SlowTable()
    playbooks._base_id = "appPLAY"
    playbooks._table_name = "tblPlaybooks"
    playbooks._cache_ttl = 60.0
    playbooks._lock = threading.Lock()
    playbooks._cache = []
    playbooks._last_refresh = 0.0
    _hammer(playbooks.list)
    assert playbooks._table.calls == 1
    assert playbooks._cache

    settings = AirtableSettingsService.__new__(AirtableSettingsService)
    shared = SlowTable()
    settings._table = lambda: shared
    settings._base_id = "appSET"
    settings._table_id = "tblSettings"
    settings._table_name = "App Settings"
    settings._ready = True
    settings._lock = threading.Lock()
    settings._cache = {}
    settings._cache_ts = 0.0

    async def hit():
        await settings.get()

    def run():
        asyncio.run(hit())

    _hammer(run)
    assert shared.calls == 1
