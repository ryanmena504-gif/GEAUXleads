"""
User settings store backed by Airtable instead of MongoDB.

The app's real data already lives in Airtable, so keeping the small
key-value settings doc there removes the MongoDB Atlas dependency
entirely. Settings live in a dedicated table (default "App Settings",
overridable via AIRTABLE_SETTINGS_TABLE) with one record per key:

    Key   (single line text, primary field) — e.g. "daily_outreach_target"
    Value (long text)                       — the string value

The table is created automatically on first use when the API token has
schema write scope. If creation is not permitted, the service reports a
clear error and the settings endpoints fall back to defaults.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

import httpx
from pyairtable import Api

from services.user_settings_service import DEFAULTS, validate_patch

log = logging.getLogger("bloodhound.airtable_settings")

META_TABLES_URL = "https://api.airtable.com/v0/meta/bases/{base_id}/tables"
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
                table_id = self._create_table()
            else:
                table_id = table.id
            self._table_id = table_id
            self._ready = True
            log.info("Airtable settings store ready (table %s)", self._table_name)

    def _create_table(self) -> str:
        payload = {
            "name": self._table_name,
            "description": "App settings key-value store (managed by the GEAUXleads backend — do not delete).",
            "fields": [
                {"name": "Key", "type": "singleLineText"},
                {"name": "Value", "type": "multilineText"},
            ],
        }
        try:
            r = httpx.post(
                META_TABLES_URL.format(base_id=self._base_id),
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=20,
            )
        except Exception as e:  # noqa: BLE001
            raise AirtableSettingsError(
                f"Could not create the '{self._table_name}' table: {e}. "
                f"Create it manually in Airtable with fields 'Key' (single line text) "
                f"and 'Value' (long text)."
            ) from e
        if r.status_code == 403:
            raise AirtableSettingsError(
                f"The Airtable token cannot create the '{self._table_name}' table "
                f"(403 — needs schema.bases:write). Create it manually in Airtable "
                f"with fields 'Key' (single line text) and 'Value' (long text)."
            )
        if r.status_code >= 300:
            raise AirtableSettingsError(
                f"Could not create the '{self._table_name}' table "
                f"(Airtable returned {r.status_code}). Create it manually in Airtable "
                f"with fields 'Key' (single line text) and 'Value' (long text)."
            )
        return r.json()["id"]

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
        except AirtableSettingsError:
            raise
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
