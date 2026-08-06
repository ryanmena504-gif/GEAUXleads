"""
Contact handoff log — every time Ryan taps Text or Email on a lead, we log
ONE event immediately. This is independent of whichever Mail/Messages
account the device ultimately uses to send: iOS Mail on iPhone picks
account A, Mac Mail on laptop picks account B — Bloodhound just records
that a handoff was fired, so nothing gets lost between sessions/devices.

Draft-only, no send. This module never touches a messaging API.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient

log = logging.getLogger("bloodhound.handoffs")

COLLECTION = "contact_handoffs"
CHANNELS = {"text", "email"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _device_hint(user_agent: Optional[str]) -> str:
    ua = (user_agent or "").lower()
    if not ua:
        return "unknown"
    if "iphone" in ua:
        return "iphone"
    if "ipad" in ua:
        return "ipad"
    if "android" in ua:
        return "android"
    if "macintosh" in ua or "mac os x" in ua:
        return "mac"
    if "windows" in ua:
        return "windows"
    if "linux" in ua:
        return "linux"
    return "unknown"


class HandoffService:
    def __init__(self, mongo_url: str, db_name: str):
        self._client = AsyncIOMotorClient(mongo_url)
        self._db = self._client[db_name]
        self._col = self._db[COLLECTION]

    @staticmethod
    def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
        if not doc:
            return doc
        return {k: v for k, v in doc.items() if k != "_id"}

    async def create(self, payload: Dict[str, Any], user_agent: Optional[str] = None) -> Dict[str, Any]:
        channel = (payload.get("channel") or "").lower()
        if channel not in CHANNELS:
            raise ValueError("channel must be 'text' or 'email'")
        doc = {
            "handoff_id": str(uuid.uuid4()),
            "opportunity_id": payload.get("opportunity_id"),
            "opportunity_name": payload.get("opportunity_name"),
            "channel": channel,
            "recipient": payload.get("recipient"),
            "device_hint": _device_hint(user_agent),
            "user_agent": (user_agent or "")[:280],
            "at": _now(),
        }
        await self._col.insert_one(doc)
        return self._serialize(doc)

    async def list_for_opportunity(self, opportunity_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        cur = (
            self._col.find({"opportunity_id": opportunity_id})
            .sort("at", -1)
            .limit(max(1, min(limit, 200)))
        )
        return [self._serialize(d) async for d in cur]

    async def list_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self._col.find({}).sort("at", -1).limit(max(1, min(limit, 500)))
        return [self._serialize(d) async for d in cur]


_singleton: Optional[HandoffService] = None


def get_handoff_service() -> Optional[HandoffService]:
    global _singleton
    if _singleton is not None:
        return _singleton
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not (mongo_url and db_name):
        return None
    _singleton = HandoffService(mongo_url, db_name)
    return _singleton
