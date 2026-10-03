"""
User preferences store — a single-document MongoDB collection holding
Ryan's app-level settings (e.g. which sender email should appear on
mailto: drafts). No credentials or messaging-provider config lives here;
the app never sends anything on its own. Just preference data.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorClient

log = logging.getLogger("bloodhound.user_settings")

COLLECTION = "user_settings"
SINGLETON_KEY = "singleton"

# Whitelist of keys Ryan can update. Anything else is silently dropped so
# the endpoint can never be used as a general document editor.
EDITABLE_KEYS = {
    "sender_email",
    "sender_name",
    "sender_phone",
    "sender_mailing_address",
    "email_provider",
    "daily_outreach_target",
}

# Allowed email-provider modes for building compose URLs. Gmail's compose
# URL supports `authuser` which pins the sending account. Outlook Web has
# a similar deeplink. Apple Mail falls back to plain mailto:.
ALLOWED_EMAIL_PROVIDERS = {"gmail", "outlook", "apple"}

# Ryan's fixed sender identity for The Shirtless Handyman. Native device
# handoff is the default: it opens the mail composer configured on the iPhone
# Ryan is actually using instead of a web inbox on a borrowed tablet.
DEFAULTS: Dict[str, Any] = {
    "sender_email": "ryanmena@theshirtlesshandyman.com",
    "sender_name": "Ryan Mena",
    "sender_phone": "(504) 264-4919",
    "sender_mailing_address": "",
    "email_provider": "apple",
    # Daily outreach target — how many leads Ryan wants to contact per day.
    # Stored as a string because update() normalizes values to strings;
    # readers parse it with _daily_target().
    "daily_outreach_target": "10",
}


def _daily_target(settings: Dict[str, Any]) -> int:
    """Parse the daily outreach target, clamped to 1..50. Never raises."""
    try:
        n = int(str(settings.get("daily_outreach_target") or "10").strip())
    except (TypeError, ValueError):
        return 10
    return max(1, min(50, n))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_patch(patch: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Whitelist + validate a settings patch. Shared by every settings backend.
    Returns the cleaned {key: string-or-None} map. Raises ValueError on bad input."""
    clean: Dict[str, Optional[str]] = {}
    for k, v in (patch or {}).items():
        if k not in EDITABLE_KEYS:
            continue
        if v is None:
            clean[k] = None
            continue
        s = str(v).strip()
        if k == "sender_email":
            # Cheap guard — a real email has an @ and a dot. Anything else
            # is either an accidental keystroke or an attack vector.
            if s and ("@" not in s or "." not in s.split("@")[-1]):
                raise ValueError("sender_email must look like an email address")
        if k == "email_provider":
            low = s.lower()
            if low and low not in ALLOWED_EMAIL_PROVIDERS:
                raise ValueError(
                    f"email_provider must be one of {sorted(ALLOWED_EMAIL_PROVIDERS)}"
                )
            s = low
        if k == "daily_outreach_target":
            try:
                n = int(s)
            except (TypeError, ValueError):
                raise ValueError("daily_outreach_target must be a whole number")
            if not 1 <= n <= 50:
                raise ValueError("daily_outreach_target must be between 1 and 50")
            s = str(n)
        clean[k] = s or None
    return clean


class UserSettingsService:
    def __init__(self, mongo_url: str, db_name: str):
        self._client = AsyncIOMotorClient(mongo_url)
        self._col = self._client[db_name][COLLECTION]

    @staticmethod
    def _serialize(doc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        merged = dict(DEFAULTS)
        if doc:
            for k, v in doc.items():
                if k in ("_id", "key"):
                    continue
                merged[k] = v
        return merged

    async def get(self) -> Dict[str, Any]:
        doc = await self._col.find_one({"key": SINGLETON_KEY})
        settings = self._serialize(doc)
        # Gmail was a legacy default that can open an inbox instead of a
        # compose window on iPhone. Move that default to native Mail. An
        # explicit future Outlook choice is still respected.
        if settings.get("email_provider") == "gmail":
            settings["email_provider"] = "apple"
        return settings

    async def update(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        clean = validate_patch(patch)
        if not clean:
            return await self.get()
        clean["updated_at"] = _now()
        await self._col.update_one(
            {"key": SINGLETON_KEY},
            {"$set": clean, "$setOnInsert": {"key": SINGLETON_KEY}},
            upsert=True,
        )
        return await self.get()


_singleton: Optional[Any] = None


def get_user_settings_service() -> Optional[Any]:
    """Return the active settings store.

    Prefers Airtable — the app's primary store, already proven reachable —
    so there is no dependency on MongoDB Atlas. Falls back to Mongo when
    Airtable is not configured, else None (defaults only).
    """
    global _singleton
    if _singleton is not None:
        return _singleton
    if (
        os.environ.get("AIRTABLE_ENABLED", "").lower() == "true"
        and os.environ.get("AIRTABLE_API_KEY")
        and os.environ.get("AIRTABLE_BASE_ID")
    ):
        from services.airtable_settings_service import AirtableSettingsService

        table = os.environ.get("AIRTABLE_SETTINGS_TABLE", "App Settings")
        _singleton = AirtableSettingsService(
            os.environ["AIRTABLE_API_KEY"], os.environ["AIRTABLE_BASE_ID"], table
        )
        log.info("User settings service: using Airtable-backed store")
        return _singleton
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if mongo_url and db_name:
        _singleton = UserSettingsService(mongo_url, db_name)
        log.info("User settings service: using MongoDB-backed store")
        return _singleton
    log.warning("User settings service: no store available — using defaults only")
    return None
