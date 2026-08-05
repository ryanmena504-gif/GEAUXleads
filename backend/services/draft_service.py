"""
Outreach draft store — Mongo-backed CRUD for the Draft a Note feature.

Draft-only. This module NEVER sends email, SMS, DMs, webhooks, or triggers
outreach in any way. `review_status="Approved for manual send"` is a
purely informational label reflecting the operator's decision — it does
not initiate any delivery.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient

log = logging.getLogger("bloodhound.drafts")

COLLECTION = "outreach_drafts"

REVIEW_STATUSES = {
    "Draft",
    "Ready for Ryan review",
    "Approved for manual send",
    "Archived",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DraftService:
    def __init__(self, mongo_url: str, db_name: str):
        self._client = AsyncIOMotorClient(mongo_url)
        self._db = self._client[db_name]
        self._col = self._db[COLLECTION]

    @staticmethod
    def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
        if not doc:
            return doc
        out = {k: v for k, v in doc.items() if k != "_id"}
        return out

    async def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        draft_id = str(uuid.uuid4())
        now = _now()
        status = payload.get("review_status") or "Draft"
        if status not in REVIEW_STATUSES:
            status = "Draft"
        doc = {
            "draft_id": draft_id,
            "opportunity_id": payload.get("opportunity_id"),
            "opportunity_name": payload.get("opportunity_name"),
            "selected_playbook": payload.get("selected_playbook"),
            "subject": payload.get("subject") or "",
            "body": payload.get("body") or "",
            "internal_note": payload.get("internal_note") or "",
            "review_status": status,
            "created_at": now,
            "updated_at": now,
        }
        await self._col.insert_one(doc)
        return self._serialize(doc)

    async def list_for_opportunity(self, opportunity_id: str) -> List[Dict[str, Any]]:
        cur = self._col.find({"opportunity_id": opportunity_id}).sort("updated_at", -1)
        return [self._serialize(d) async for d in cur]

    async def list_by_status(self, status: str, limit: int = 200) -> List[Dict[str, Any]]:
        """Return every draft with the given review_status, newest first."""
        cur = (
            self._col.find({"review_status": status})
            .sort("updated_at", -1)
            .limit(limit)
        )
        return [self._serialize(d) async for d in cur]

    async def counts_by_status(self) -> Dict[str, int]:
        """Return {status: count} across all drafts. Empty statuses are omitted."""
        pipeline = [{"$group": {"_id": "$review_status", "n": {"$sum": 1}}}]
        out: Dict[str, int] = {}
        async for doc in self._col.aggregate(pipeline):
            key = doc.get("_id")
            if isinstance(key, str):
                out[key] = int(doc.get("n") or 0)
        return out

    async def get(self, draft_id: str) -> Optional[Dict[str, Any]]:
        doc = await self._col.find_one({"draft_id": draft_id})
        return self._serialize(doc) if doc else None

    async def update(self, draft_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {"subject", "body", "internal_note", "selected_playbook", "review_status"}
        clean: Dict[str, Any] = {k: v for k, v in patch.items() if k in allowed and v is not None}
        if "review_status" in clean and clean["review_status"] not in REVIEW_STATUSES:
            clean.pop("review_status")
        clean["updated_at"] = _now()
        r = await self._col.find_one_and_update(
            {"draft_id": draft_id}, {"$set": clean}, return_document=True,
        )
        return self._serialize(r) if r else None

    async def delete(self, draft_id: str) -> bool:
        r = await self._col.delete_one({"draft_id": draft_id})
        return r.deleted_count > 0


_singleton: Optional[DraftService] = None


def get_draft_service() -> Optional[DraftService]:
    global _singleton
    if _singleton is not None:
        return _singleton
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not (mongo_url and db_name):
        log.warning("Draft service: MONGO_URL/DB_NAME missing — drafts unavailable")
        return None
    _singleton = DraftService(mongo_url, db_name)
    return _singleton
