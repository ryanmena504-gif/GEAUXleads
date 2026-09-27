"""
User settings store backed by Airtable instead of MongoDB.

The app's real data already lives in Airtable, so keeping the small
key-value settings doc there removes the MongoDB Atlas dependency
entirely. Settings live in a dedicated table (default "App Settings",
overridable via AIRTABLE_SETTINGS_TABLE) with one record per key:

    Key   (single line text, primary field) — e.g. "daily_outreach_target"
    Value (long text)                       — the string value

The app never creates this table (or any Airtable field/table). If it is
missing, reads fall back to defaults and saves fail with a clear error
telling Ryan to create it in Airtable.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

from pyairtable import Api

from services.user_settings_service import DEFAULTS, validate_patch

log = logging.getLogger("bloodhound.airtable_settings")

CACHE_TTL = 60.0


class AirtableSettingsError(Exception):
    """The settings store exists but is unusable (e.g. table cannot be created)."""


class AirtableSettingsService:
    # Same async interface as the Mongo-backed UserSettingsService so the
    # server endpoints work unchanged. pyairtable is sync; settings calls
    # are tiny and infrequent, matching the existing opportunity-service
    # pattern of inline sync Airtable calls.

    def __init__(self, api_key: str, base_id: str, table_name: str = "App Settings"):
        self._api_key = api_key
        self._base_id = base_id
        self._table_name = table_name
        self._api = Api(api_key)
        self._table_id: Optional[str] = None
        self._ready = False
        self._lock = threading.Lock()
        self._cache: Dict[str, Any] = {}
        self._cache_ts = 0.0

    @property
    def store_available(self) -> bool:
        """False when the table could not be bootstrapped — endpoints should
        report persisted=False so the UI shows the 'won't stick' notice."""
        try:
            self._ensure_table()
        except AirtableSettingsError:
            return False
        return True

    # ----- table bootstrap -----
    def _ensure_table(self) -> None:
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            try:
                schema = self._api.base(self._base_id).schema()
            except Exception as e:  # noqa: BLE001
                raise AirtableSettingsError(
                    f"Could not read Airtable schema: {e}"
                ) from e
            table = next(
                (
                    t
                    for t in schema.tables
                    if t.name == self._table_name or t.id == self._table_name
                ),
                None,
            )
            if table is None:
                try:
                    visible = sorted(t.name for t in schema.tables)
                except Exception:  # noqa: BLE001
                    visible = []
                seen = ", ".join(visible) if visible else "none visible"
                raise AirtableSettingsError(
                    f"The '{self._table_name}' table doesn't exist in Airtable. "
                    f"GEAUXleads never creates Airtable tables — create it in Airtable "
                    f"with fields 'Key' (single line text) and 'Value' (long text), "
                    f"or set AIRTABLE_SETTINGS_TABLE to an existing table's name. "
                    f"Tables visible right now: {seen}."
                )
            else:
                table_id = table.id
            self._table_id = table_id
            self._ready = True
            log.info("Airtable settings store ready (table %s)", self._table_name)

    def _table(self):
        self._ensure_table()
        return self._api.table(self._base_id, self._table_id or self._table_name)

    # ----- interface -----
    async def get(self) -> Dict[str, Any]:
        merged = dict(DEFAULTS)
        # Gmail was a legacy default that can open an inbox instead of a
        # compose window on iPhone. Move that default to native Mail.
        if merged.get("email_provider") == "gmail":
            merged["email_provider"] = "apple"
        now = time.monotonic()
        if self._cache and now - self._cache_ts < CACHE_TTL:
            merged.update(self._cache)
            return merged
        try:
            records = self._table().all()
        except AirtableSettingsError as e:
            # Missing table: never create it, never crash — use defaults.
            log.warning("Airtable settings unavailable — returning defaults: %s", e)
            return merged
        except Exception:  # noqa: BLE001
            log.exception("Airtable settings read failed — returning defaults")
            return merged
        stored = {}
        for rec in records:
            fields = rec.get("fields", {})
            k = fields.get("Key")
            v = fields.get("Value")
            if k and v not in (None, ""):
                stored[k] = v
        self._cache = stored
        self._cache_ts = now
        merged.update(stored)
        return merged

    async def update(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        clean = validate_patch(patch)  # raises ValueError on bad input
        if not clean:
            return await self.get()
        try:
            table = self._table()
            existing = {}
            for rec in table.all():
                k = rec.get("fields", {}).get("Key")
                if k:
                    existing[k] = rec["id"]
            for k, v in clean.items():
                # Airtable can't store None in a text field; empty reverts to default on read.
                value = v if v is not None else ""
                if k in existing:
                    table.update(existing[k], {"Value": value})
                else:
                    table.create({"Key": k, "Value": value})
        except AirtableSettingsError:
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("Airtable settings write failed")
            raise AirtableSettingsError(f"Could not save settings: {e}") from e
        self._cache = {}
        self._cache_ts = 0.0
        return await self.get()
