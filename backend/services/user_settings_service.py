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
EDITABLE_KEYS = {"sender_email", "sender_name", "sender_phone", "email_provider"}

# Allowed email-provider modes for building compose URLs. Gmail's compose
# URL supports `authuser` which pins the sending account. Outlook Web has
# a similar deeplink. Apple Mail falls back to plain mailto:.
ALLOWED_EMAIL_PROVIDERS = {"gmail", "outlook", "apple"}

# Ryan's fixed sender identity for The Shirtless Handyman. Default provider
# is Apple Mail (mailto:) — the device's default mail app decides which
# account the message sends from. Bloodhound never claims control over that.
DEFAULTS: Dict[str, Any] = {
    "sender_email": "ryanmena@theshirtlesshandyman.com",
    "sender_name": "Ryan Mena",
    "sender_phone": "(504) 264-4919",
    "email_provider": "apple",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        return self._serialize(doc)

    async def update(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        clean: Dict[str, Any] = {}
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
            clean[k] = s or None
        if not clean:
            return await self.get()
        clean["updated_at"] = _now()
        await self._col.update_one(
            {"key": SINGLETON_KEY},
            {"$set": clean, "$setOnInsert": {"key": SINGLETON_KEY}},
            upsert=True,
        )
        return await self.get()


_singleton: Optional[UserSettingsService] = None


def get_user_settings_service() -> Optional[UserSettingsService]:
    global _singleton
    if _singleton is not None:
        return _singleton
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not (mongo_url and db_name):
        log.warning("User settings service: MONGO_URL/DB_NAME missing — using defaults only")
        return None
    _singleton = UserSettingsService(mongo_url, db_name)
    return _singleton
