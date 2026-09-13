"""
Mongo-backed cache for Perplexity research answers. A second tap on
"Who runs this?" for the same lead within `_TTL_HOURS` returns the
stored answer instead of paying Perplexity again.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorClient

log = logging.getLogger("bloodhound.research_cache")

_COLLECTION = "research_cache"
_TTL_HOURS = 24 * 7  # a week — lead facts don't change often

_client: Optional[AsyncIOMotorClient] = None
_db_name: Optional[str] = None


def _db():
    global _client, _db_name
    if _client is None:
        url = os.environ.get("MONGO_URL")
        _db_name = os.environ.get("DB_NAME")
        if not url or not _db_name:
            raise RuntimeError("MONGO_URL / DB_NAME not configured")
        _client = AsyncIOMotorClient(url)
    return _client[_db_name][_COLLECTION]


def _key(research_type: str, record_id: str) -> str:
    return f"{research_type}::{record_id}"


async def get_cached(research_type: str, record_id: str) -> Optional[Dict[str, Any]]:
    coll = _db()
    doc = await coll.find_one({"_key": _key(research_type, record_id)})
    if not doc:
        return None
    generated_at = doc.get("result", {}).get("generated_at")
    if generated_at:
        try:
            when = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - when > timedelta(hours=_TTL_HOURS):
                return None
        except (ValueError, TypeError):
            pass
    result = doc.get("result") or {}
    result["_cached"] = True
    return result


async def set_cached(research_type: str, record_id: str, result: Dict[str, Any]) -> None:
    coll = _db()
    await coll.update_one(
        {"_key": _key(research_type, record_id)},
        {
            "$set": {
                "_key": _key(research_type, record_id),
                "research_type": research_type,
                "record_id": record_id,
                "result": result,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )


async def clear_cached(research_type: str, record_id: str) -> None:
    """Force a fresh Perplexity call on next request."""
    coll = _db()
    await coll.delete_one({"_key": _key(research_type, record_id)})
