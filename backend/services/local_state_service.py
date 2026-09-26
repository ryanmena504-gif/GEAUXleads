"""
Bloodhound-local archive state — hides records in the UI ONLY. Never
mutates Airtable or Make. Namespaced by (workspace, feed) so record IDs
that overlap across Leads/Discovery feeds don't collide.
"""
from __future__ import annotations
import logging, os
from datetime import datetime, timezone
from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorClient

log = logging.getLogger("bloodhound.local_state")
_COLL = "bloodhound_local_state"
_WORKSPACE = "solo"
_client = None

_ALLOWED_FEEDS = frozenset({
    "leads", "property_managers", "re_agents", "landlords", "investors",
})

def _db():
    global _client
    if _client is None:
        url = os.environ.get("MONGO_URL"); name = os.environ.get("DB_NAME")
        if not url or not name: raise RuntimeError("MONGO_URL / DB_NAME not configured")
        _client = AsyncIOMotorClient(url)
    return _client[os.environ["DB_NAME"]][_COLL]

def _validate_feed(feed: str) -> str:
    if feed not in _ALLOWED_FEEDS:
        raise ValueError(f"unknown feed '{feed}'")
    return feed

async def list_archived(feed: str) -> List[str]:
    _validate_feed(feed)
    cur = _db().find({"workspace": _WORKSPACE, "feed": feed, "hidden_at": {"$ne": None}}, {"record_id": 1})
    return [d["record_id"] async for d in cur]

async def archive_many(feed: str, record_ids: List[str]) -> int:
    _validate_feed(feed)
    if not record_ids: return 0
    now = datetime.now(timezone.utc).isoformat()
    ops = []
    from pymongo import UpdateOne
    for rid in record_ids:
        ops.append(UpdateOne(
            {"workspace": _WORKSPACE, "feed": feed, "record_id": rid},
            {"$set": {"workspace": _WORKSPACE, "feed": feed, "record_id": rid, "hidden_at": now}},
            upsert=True,
        ))
    res = await _db().bulk_write(ops)
    return (res.upserted_count or 0) + (res.modified_count or 0)

async def unarchive_many(feed: str, record_ids: List[str]) -> int:
    _validate_feed(feed)
    if not record_ids: return 0
    res = await _db().delete_many({
        "workspace": _WORKSPACE, "feed": feed, "record_id": {"$in": record_ids},
    })
    return res.deleted_count or 0
