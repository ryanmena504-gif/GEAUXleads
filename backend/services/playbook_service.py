"""
Read-only projection of the Airtable `Message Playbooks` table for the
Draft a Note feature. Never exposes credentials to the frontend — the
server returns a small, safe DTO with just the fields the UI needs.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from pyairtable import Api

log = logging.getLogger("bloodhound.playbooks")


PLAYBOOKS_TABLE_ID = "tble13PxRqtWfPHzb"

# Exact Airtable field name (case-sensitive) → internal snake_case key.
FIELD_MAP: Dict[str, str] = {
    "Playbook Name":     "name",
    "Playbook ID":       "playbook_id",
    "Audience Type":     "audience_type",
    "Channel":           "channel",
    "Trigger / Use Case": "trigger",
    "Default Subject":   "default_subject",
    "Default Draft":     "default_draft",
    "Editable Variables": "editable_variables",
    "Voice Rules":       "voice_rules",
    "Approval Note":     "approval_note",
    "Status":            "status",
}

# Audience type slug (URL-safe) so the frontend can auto-select the right
# template from an opportunity's `project_type` without exposing raw
# Airtable single-select values.
AUDIENCE_SLUGS = {
    "Builder / Remodeler": "builder",
    "Interior Designer":   "designer",
    "Pool / Outdoor Living": "pool_outdoor",
}


def _to_dto(record: Dict[str, Any]) -> Dict[str, Any]:
    fields = record.get("fields", {}) or {}
    dto: Dict[str, Any] = {"id": record.get("id")}
    for at_name, snake in FIELD_MAP.items():
        dto[snake] = fields.get(at_name)
    audience = dto.get("audience_type") or ""
    dto["audience_slug"] = AUDIENCE_SLUGS.get(audience) or (
        audience.lower().replace(" ", "_").replace("/", "_")[:32] if audience else None
    )
    return dto


class PlaybookService:
    def __init__(self, api_key: str, base_id: str, table_id: str = PLAYBOOKS_TABLE_ID,
                 cache_ttl: float = 60.0):
        self._api = Api(api_key)
        self._table = self._api.table(base_id, table_id)
        self._cache_ttl = cache_ttl
        self._lock = threading.Lock()
        self._cache: List[Dict[str, Any]] = []
        self._last_refresh: float = 0.0

    def _refresh(self, force: bool = False) -> None:
        now = time.time()
        if not force and (now - self._last_refresh) < self._cache_ttl and self._cache:
            return
        try:
            records = self._table.all()
        except Exception:
            log.exception("Playbooks: refresh failed")
            return
        dtos = [_to_dto(r) for r in records]
        # Only expose active/draft-ready playbooks — hide anything marked
        # Archived or missing a Default Draft body.
        def _live(p: Dict[str, Any]) -> bool:
            status = (p.get("status") or "").lower() if isinstance(p.get("status"), str) else ""
            if "archived" in status or "retired" in status:
                return False
            return bool(p.get("default_draft"))
        with self._lock:
            self._cache = [d for d in dtos if _live(d)]
            self._last_refresh = now

    def list(self) -> List[Dict[str, Any]]:
        self._refresh()
        with self._lock:
            return list(self._cache)

    def get(self, playbook_id: str) -> Optional[Dict[str, Any]]:
        """Match by Airtable record id OR by Playbook ID slug."""
        for p in self.list():
            if p.get("id") == playbook_id or p.get("playbook_id") == playbook_id:
                return p
        return None

    # ------------------------------------------------------------------
    # Write path — Ryan can tweak Default Subject / Default Draft from
    # Settings without opening Airtable. This is the ONLY writable path
    # from the Bloodhound UI into the Message Playbooks table; the
    # allowlist below is enforced server-side.
    # ------------------------------------------------------------------
    _EDITABLE_AIRTABLE_FIELDS = {
        "default_subject": "Default Subject",
        "default_draft":   "Default Draft",
    }

    def update(self, playbook_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update the whitelisted fields on a playbook record and bust the
        cache. Silently drops anything not in the allowlist. Returns the
        fresh DTO or None if the record isn't found."""
        record = self.get(playbook_id)
        if not record:
            return None
        record_id = record.get("id")
        if not record_id:
            return None
        clean_airtable: Dict[str, Any] = {}
        for snake, at_field in self._EDITABLE_AIRTABLE_FIELDS.items():
            if snake in patch and isinstance(patch[snake], str):
                clean_airtable[at_field] = patch[snake]
        if not clean_airtable:
            return record
        try:
            self._table.update(record_id, clean_airtable)
        except Exception:
            log.exception("Playbooks: Airtable update failed for %s", record_id)
            raise
        # Bust cache so the next read serves the fresh copy.
        with self._lock:
            self._last_refresh = 0.0
        return self.get(playbook_id)


_singleton: Optional[PlaybookService] = None


def get_playbook_service() -> Optional[PlaybookService]:
    global _singleton
    if _singleton is not None:
        return _singleton
    if os.environ.get("AIRTABLE_ENABLED", "").lower() != "true":
        return None
    api_key = os.environ.get("AIRTABLE_API_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    if not (api_key and base_id):
        return None
    try:
        _singleton = PlaybookService(api_key, base_id)
        log.info("Playbook service: initialized against %s", PLAYBOOKS_TABLE_ID)
        return _singleton
    except Exception:
        log.exception("Playbook service init failed")
        return None
