"""
Discovery Handoff Notes — tracks which records in each discovery feed
have already been surfaced as "actionable" (outreach-gate unlocked AND
contact info present). When Make flips a locked record to actionable,
this service tags it as `is_freshly_actionable` on the very next
API response so Ryan sees a "New contact" badge and the row floats
to the top of the feed. Once he opens the app the tag persists for
one full session-window, then decays back to a regular row.

Storage: one Mongo doc per feed (`discovery_handoff` collection).
  { "feed": "real_estate_agents", "seen_ids": ["rec1", "rec2", ...],
    "updated_at": iso-timestamp }

Zero writes to Airtable. Zero LLM calls. Read-mark-write cycle stays
strictly on the Bloodhound side.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Set

from motor.motor_asyncio import AsyncIOMotorClient

log = logging.getLogger("bloodhound.discovery_handoff")

COLLECTION = "discovery_handoff"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DiscoveryHandoffService:
    def __init__(self, mongo_url: str, db_name: str):
        self._client = AsyncIOMotorClient(mongo_url)
        self._col = self._client[db_name][COLLECTION]

    async def _seen(self, feed: str) -> Set[str]:
        doc = await self._col.find_one({"feed": feed})
        if not doc:
            return set()
        return set(doc.get("seen_ids") or [])

    async def _persist(self, feed: str, seen_ids: Set[str]) -> None:
        await self._col.update_one(
            {"feed": feed},
            {"$set": {"seen_ids": list(seen_ids), "updated_at": _now()},
             "$setOnInsert": {"feed": feed}},
            upsert=True,
        )

    async def mark_fresh(self, feed: str, current_actionable_ids: Iterable[str]) -> Set[str]:
        """Return the subset of `current_actionable_ids` never seen before.

        On first call for a feed, ALL current ids are considered fresh — this
        is fine because on production the first call happens right after
        Claude seeds the record with contact info, which IS the moment we
        want to surface it. Subsequent calls only return newly-added ids.
        """
        current = set(current_actionable_ids or [])
        previously_seen = await self._seen(feed)
        fresh = current - previously_seen
        # Drop ids that dropped out of actionable (e.g. Make re-locked them)
        # so they get surfaced again when they come back — otherwise a
        # record that flickers in and out never re-marks. Keeping only ids
        # currently in the actionable set is the honest behaviour.
        await self._persist(feed, current)
        return fresh

    async def clear(self, feed: str) -> None:
        await self._col.delete_one({"feed": feed})


_singleton: Optional[DiscoveryHandoffService] = None


def get_discovery_handoff_service() -> Optional[DiscoveryHandoffService]:
    global _singleton
    if _singleton is not None:
        return _singleton
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not (mongo_url and db_name):
        log.warning("Discovery handoff service: MONGO_URL/DB_NAME missing")
        return None
    _singleton = DiscoveryHandoffService(mongo_url, db_name)
    return _singleton


# --------- Feed keys used across endpoints ---------
FEED_PROPERTY_MANAGERS = "property_managers"
FEED_REAL_ESTATE_AGENTS = "real_estate_agents"
FEED_INVESTORS = "investors"


def is_actionable_agent(agent: dict) -> bool:
    """Real estate agent is actionable when the outreach gate is unlocked
    AND at least one contact channel (email or phone) is present."""
    return bool(agent.get("outreach_ready")) and bool(agent.get("email") or agent.get("phone"))


def is_actionable_investor(investor: dict) -> bool:
    return bool(investor.get("outreach_ready")) and bool(
        investor.get("email") or investor.get("phone")
    )


def is_actionable_property_manager(pm: dict) -> bool:
    """PMs don't have an Outreach Gate — they're actionable the moment
    they land in Claude's Worth-a-look bucket AND have any contact info."""
    status = (pm.get("review_status") or "").strip().lower()
    if status != "worth a look":
        return False
    return bool(pm.get("phone") or pm.get("email") or pm.get("website"))
