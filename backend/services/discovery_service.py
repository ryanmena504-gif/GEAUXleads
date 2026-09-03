"""
Discovery services — thin readers for the "discovery queue" Airtable tables
that live outside the governed Leads pipeline.

These tables (Property Manager Discovery Queue, Real Estate Agent Outreach,
Investor Intelligence, etc.) are owned by Claude + Make on the data side.
Bloodhound is strictly a read-only viewer. No writes.

Rather than duplicate the full AirtableOpportunityService (schema loading,
write allowlist, field maps), each discovery reader:
  • Reads every field on every record as-is
  • Applies snake_case normalization to the field names for the API layer
  • Caches for a short TTL (60s) so we don't hammer the API
  • Falls back to an empty list if the table doesn't exist or errors out
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional

from pyairtable import Api

log = logging.getLogger("bloodhound.discovery")


def _snake(name: str) -> str:
    """Airtable field name → snake_case key for the API layer."""
    s = re.sub(r"[^\w\s]", "", name or "").strip().replace(" ", "_")
    return s.lower()


class DiscoveryReader:
    """Read-only reader for one Airtable table. Zero writes."""

    def __init__(self, api_key: str, base_id: str, table_name: str, cache_ttl: float = 60.0):
        self._api = Api(api_key)
        self._base_id = base_id
        self._table_name = table_name
        self._table = self._api.table(base_id, table_name)
        self._cache_ttl = cache_ttl
        self._lock = threading.Lock()
        self._cache: List[Dict[str, Any]] = []
        self._last_refresh: float = 0.0
        self._last_error: Optional[str] = None

    def _record_to_dict(self, record: Dict[str, Any]) -> Dict[str, Any]:
        raw = record.get("fields", {}) or {}
        out: Dict[str, Any] = {
            "id": record.get("id"),
            "created_time": record.get("createdTime"),
        }
        for name, value in raw.items():
            out[_snake(name)] = value
        # Also keep the raw Airtable-named field dict for the DebugPanel style
        # views (never used for governed logic — read-only inspection only).
        out["_raw"] = dict(raw)
        return out

    def _needs_refresh(self) -> bool:
        return (time.time() - self._last_refresh) > self._cache_ttl

    def all(self) -> List[Dict[str, Any]]:
        with self._lock:
            if not self._needs_refresh():
                return list(self._cache)
        # Do the refresh outside the lock to avoid blocking readers.
        try:
            records = self._table.all()
            items = [self._record_to_dict(r) for r in records]
            with self._lock:
                self._cache = items
                self._last_refresh = time.time()
                self._last_error = None
            log.info("Discovery '%s': loaded %d records", self._table_name, len(items))
            return list(items)
        except Exception as e:  # noqa: BLE001
            log.warning("Discovery '%s' fetch failed: %s", self._table_name, e)
            with self._lock:
                self._last_error = str(e)[:220]
                return list(self._cache)  # stale beats nothing


# ---------------------------------------------------------------------------
# Property Manager Discovery Queue
# ---------------------------------------------------------------------------
# The Airtable base has a table named "Property Manager Discovery Queue" with
# 23 property management companies. Each has a `Review Status` field with one
# of: "New" / "Worth a look" / "Not relevant …" / "Promoted to Leads".
# Only "Worth a look" records surface as real candidates on the Discovery UI.
# Everything else is filtered out unless the caller passes status="all".
# ---------------------------------------------------------------------------
PROPERTY_MANAGER_TABLE = "Property Manager Discovery Queue"

_pm_reader: Optional[DiscoveryReader] = None


def get_property_manager_reader() -> Optional[DiscoveryReader]:
    """Lazy singleton — returns None if Airtable isn't configured."""
    global _pm_reader
    if _pm_reader is not None:
        return _pm_reader
    api_key = os.environ.get("AIRTABLE_API_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    enabled = os.environ.get("AIRTABLE_ENABLED", "").lower() == "true"
    if not (enabled and api_key and base_id):
        return None
    _pm_reader = DiscoveryReader(api_key, base_id, PROPERTY_MANAGER_TABLE)
    return _pm_reader


# Review-Status values Claude ships (per user handoff).
REVIEW_STATUS_WORTH_A_LOOK = "worth a look"
REVIEW_STATUS_PROMOTED = "promoted to leads"


def _normalize_status(v: Any) -> str:
    return (str(v or "").strip().lower())


def _pick_first(row: Dict[str, Any], keys: List[str]) -> Any:
    """Return the first non-empty value from a candidate key list.

    The Property Manager table's field names aren't fully locked, so we look
    for a few common variants (case-insensitive after _snake) and take the
    first one that has a value. Never invents data — if none match, returns None.
    """
    for k in keys:
        v = row.get(k)
        if v not in (None, "", [], {}):
            return v
    return None


def list_property_managers(status: str = "worth_a_look") -> List[Dict[str, Any]]:
    """Return the property manager discovery queue, filtered by review status.

    status: "worth_a_look" (default) | "all" | any exact Review Status value
    """
    reader = get_property_manager_reader()
    if reader is None:
        return []
    rows = reader.all()

    if status != "all":
        wanted = _normalize_status(status.replace("_", " "))
        rows = [r for r in rows if _normalize_status(r.get("review_status")) == wanted]

    # Sort: fresh records first (uses Airtable's createdTime metadata), then id.
    rows.sort(key=lambda r: (r.get("created_time") or "", r.get("id") or ""), reverse=True)

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            "id": r.get("id"),
            "name": _pick_first(r, ["business_name", "name", "company_name", "company", "property_manager", "property_management_company"]),
            "phone": _pick_first(r, ["phone", "phone_number", "contact_phone", "main_phone"]),
            "website": _pick_first(r, ["website", "url", "web", "homepage"]),
            "email": _pick_first(r, ["email", "contact_email"]),
            "address": _pick_first(r, ["address", "office_address", "location"]),
            "notes": _pick_first(r, ["notes", "note", "why", "context", "why_worth_a_look", "why_it_matters"]),
            "portfolio_size": _pick_first(r, ["portfolio_size", "units", "portfolio", "unit_count"]),
            "review_status": r.get("review_status"),
            "date_discovered": r.get("date_discovered"),
            "created_time": r.get("created_time"),
        })
    return out


def property_manager_status_counts() -> Dict[str, int]:
    """Count records per Review Status — used to render tab badges."""
    reader = get_property_manager_reader()
    if reader is None:
        return {}
    counts: Dict[str, int] = {}
    for r in reader.all():
        raw_status = r.get("review_status") or "Unset"
        label = raw_status if isinstance(raw_status, str) else str(raw_status)
        counts[label] = counts.get(label, 0) + 1
    return counts
