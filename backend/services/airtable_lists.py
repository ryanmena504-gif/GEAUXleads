"""One shared single-flight cache for Airtable record lists.

Every full-table or filtered ``Table.all()`` in the backend goes through
``fetch_all``. Concurrent callers for the same base, table, and query share
one download, and a second caller inside its own TTL reuses that download
instead of paging Airtable again. Only one list runs in the process at a
time, so two tables cannot page the API in parallel.

That matters on the free plan (1,000 calls a month) and because parallel
full-table pages tripped Airtable's 5-per-second limit on 2026-10-03.

Single-record reads and writes stay on the table object. Paid research
clients are not involved here and are not retried.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("bloodhound.airtable_lists")

ListLoader = Callable[[], List[Any]]


class AirtableListError(Exception):
    """A shared list failed. Waiting threads raise this, not the original."""


class _Slot:
    def __init__(self) -> None:
        self.cv = threading.Condition()
        self.inflight = False
        self.records: Optional[List[Any]] = None
        self.fetched_at = 0.0
        self.generation = 0
        self.epoch = 0
        self.waiters = 0
        self.error: Optional[BaseException] = None


_slots_guard = threading.Lock()
_slots: Dict[str, _Slot] = {}
# Process-wide: two different tables must not page Airtable at the same time.
_download_lock = threading.Lock()


def list_key(base_id: str, table: str, **query: Any) -> str:
    """Stable cache key. Query args keep a filtered list off the full table."""
    parts = [str(base_id), str(table)]
    for name in sorted(query):
        value = query[name]
        if isinstance(value, (list, tuple)):
            value = tuple(value)
        parts.append(f"{name}={value!r}")
    return "\n".join(parts)


def key_for(
    base_id: Optional[str],
    table_id: Optional[str],
    table_name: Optional[str],
    table_obj: Any,
    **query: Any,
) -> str:
    """Prefer the Airtable table id so name and id for one table share a slot.

    Readers built in tests without a base id stay isolated on the fake table
    object, so they cannot reuse another test's rows.
    """
    ident = table_id or table_name
    if not base_id or not ident:
        ident = f"obj:{id(table_obj)}"
        base_id = base_id or ""
    return list_key(str(base_id), str(ident), **query)


def key_for_reader(reader: Any, table_obj: Any, **query: Any) -> str:
    return key_for(
        getattr(reader, "_base_id", None),
        getattr(reader, "_table_id", None),
        getattr(reader, "_table_name", None),
        table_obj,
        **query,
    )


def _slot(key: str) -> _Slot:
    with _slots_guard:
        slot = _slots.get(key)
        if slot is None:
            slot = _Slot()
            _slots[key] = slot
        return slot


def _copy(records: Optional[List[Any]]) -> List[Any]:
    """Return records the caller can mutate without poisoning the cache."""
    out: List[Any] = []
    for rec in records or []:
        if isinstance(rec, dict):
            dup = dict(rec)
            fields = dup.get("fields")
            if isinstance(fields, dict):
                dup["fields"] = dict(fields)
            out.append(dup)
        else:
            out.append(rec)
    return out


def fetch_all(
    key: str,
    loader: ListLoader,
    *,
    ttl: float,
    force: bool = False,
) -> List[Any]:
    """Return every record for ``key``, downloading once for concurrent callers.

    ``ttl`` is the caller's own freshness window. ``force`` skips a snapshot
    that is already stored, but still joins a download that is already running.
    """
    slot = _slot(key)
    ttl = ttl if ttl and ttl > 0 else 0.0
    with slot.cv:
        while True:
            now = time.monotonic()
            fresh = (
                slot.error is None
                and slot.records is not None
                and (now - slot.fetched_at) < ttl
            )
            if fresh and not force:
                return _copy(slot.records)
            if slot.inflight:
                seen = slot.generation
                slot.waiters += 1
                try:
                    slot.cv.wait()
                finally:
                    slot.waiters -= 1
                if slot.generation == seen:
                    continue
                if slot.error is not None:
                    raise AirtableListError(str(slot.error)) from slot.error
                if slot.records is not None:
                    return _copy(slot.records)
                continue
            slot.inflight = True
            epoch = slot.epoch
            break

    try:
        with _download_lock:
            loaded = loader()
        records = _copy(loaded)
    except BaseException as exc:
        with slot.cv:
            slot.inflight = False
            if slot.epoch == epoch:
                slot.error = exc
                # Drop a stale success so the next read does not look fresh.
                slot.records = None
            slot.generation += 1
            slot.cv.notify_all()
        raise

    with slot.cv:
        slot.inflight = False
        slot.generation += 1
        if slot.epoch == epoch:
            slot.records = records
            slot.fetched_at = time.monotonic()
            slot.error = None
            log.debug("Airtable list %s stored %d records", key.split("\n", 1)[0], len(records))
        slot.cv.notify_all()
    return _copy(records)


def invalidate_reader(reader: Any, table_obj: Any) -> None:
    """Forget cached lists for this reader's table after a successful write."""
    base = getattr(reader, "_base_id", None)
    table_id = getattr(reader, "_table_id", None)
    table_name = getattr(reader, "_table_name", None)
    prefixes = []
    if base and table_id:
        prefixes.append(list_key(str(base), str(table_id)))
    if base and table_name:
        prefixes.append(list_key(str(base), str(table_name)))
    if not prefixes:
        prefixes.append(list_key("", f"obj:{id(table_obj)}"))
    _invalidate_prefixes(prefixes)


def _invalidate_prefixes(prefixes: List[str]) -> None:
    with _slots_guard:
        keys = list(_slots)
    for key in keys:
        if not any(key == prefix or key.startswith(prefix + "\n") for prefix in prefixes):
            continue
        slot = _slot(key)
        with slot.cv:
            slot.records = None
            slot.fetched_at = 0.0
            slot.error = None
            slot.epoch += 1
            slot.cv.notify_all()


def reset_for_tests() -> None:
    """Drop every cached list. Tests only."""
    with _slots_guard:
        _slots.clear()
