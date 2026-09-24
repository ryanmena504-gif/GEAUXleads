"""
Airtable Webhooks manager.

Owns:
  - Idempotent webhook registration against a single (base, table).
  - HMAC signature verification for incoming pings.
  - Cursor-based payload fetch after each ping.
  - In-process SSE broadcaster fanning out change notifications to
    connected frontend clients.

State (webhook_id, macSecret, cursor) lives in memory. Re-registered on
every restart — Airtable webhooks last 7 days by default, so a short-lived
preview process re-registering is fine. For long-lived production, promote
this to persistent storage.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import os
from typing import Any, Dict, List, Optional, Set

import httpx

log = logging.getLogger("bloodhound.webhook")

AIRTABLE_API = "https://api.airtable.com/v0"


class AirtableWebhookManager:
    def __init__(self, *, api_key: str, base_id: str, table_id: str, public_url: str):
        self.api_key = api_key
        self.base_id = base_id
        self.table_id = table_id
        self.notification_url = f"{public_url.rstrip('/')}/api/airtable/webhook"
        self.webhook_id: Optional[str] = None
        self.mac_secret_b64: Optional[str] = None
        self.cursor: int = 1
        self._subscribers: Set[asyncio.Queue] = set()
        self._subs_lock = asyncio.Lock()

    # ---------- HTTP helpers ----------
    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def _list(self, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
        r = await client.get(f"{AIRTABLE_API}/bases/{self.base_id}/webhooks",
                             headers=self._headers())
        r.raise_for_status()
        return r.json().get("webhooks", []) or []

    class MissingWebhookScope(Exception):
        """Raised when the Airtable PAT lacks the webhook:manage scope."""

    async def _delete(self, client: httpx.AsyncClient, webhook_id: str) -> None:
        r = await client.delete(
            f"{AIRTABLE_API}/bases/{self.base_id}/webhooks/{webhook_id}",
            headers=self._headers(),
        )
        # 404 is fine (already gone); anything else surfaces.
        if r.status_code not in (200, 204, 404):
            r.raise_for_status()

    async def _create(self, client: httpx.AsyncClient) -> Dict[str, Any]:
        payload = {
            "notificationUrl": self.notification_url,
            "specification": {
                "options": {
                    "filters": {
                        "dataTypes": ["tableData"],
                        "recordChangeScope": self.table_id,
                        "changeTypes": ["add", "update"],
                    }
                }
            },
        }
        r = await client.post(
            f"{AIRTABLE_API}/bases/{self.base_id}/webhooks",
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload,
        )
        r.raise_for_status()
        return r.json()

    # ---------- registration ----------
    async def ensure_registered(self) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                existing = await self._list(client)
            except httpx.HTTPStatusError as e:
                # 403 → PAT is missing the webhook:manage scope. That's an
                # operator config issue, not a code bug. Surface a friendly
                # one-line warning so preview logs stay readable.
                if e.response.status_code == 403:
                    raise AirtableWebhookManager.MissingWebhookScope(
                        "Airtable PAT is missing the 'webhook:manage' scope — "
                        "live push updates are disabled. Add the scope in Airtable → "
                        "Developer Hub → Personal access tokens to enable SSE."
                    ) from e
                raise
            # Clean up ANY webhook already pointing at our URL so we get a fresh secret.
            for w in existing:
                if w.get("notificationUrl") == self.notification_url:
                    log.info("Removing stale webhook %s @ %s", w.get("id"), self.notification_url)
                    await self._delete(client, w["id"])
            data = await self._create(client)
        self.webhook_id = data["id"]
        self.mac_secret_b64 = data["macSecretBase64"]
        # Airtable returns cursorForNextPayload on create; use it if present.
        self.cursor = int(data.get("cursorForNextPayload") or 1)
        log.info("Airtable webhook %s registered watching table %s (cursor=%d)",
                 self.webhook_id, self.table_id, self.cursor)

    async def unregister(self) -> None:
        if not self.webhook_id:
            return
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                await self._delete(client, self.webhook_id)
                log.info("Airtable webhook %s deleted", self.webhook_id)
            except Exception:
                log.exception("Failed to delete webhook %s", self.webhook_id)

    # ---------- signature ----------
    def verify_signature(self, body: bytes, signature_header: Optional[str]) -> bool:
        if not self.mac_secret_b64 or not signature_header:
            return False
        try:
            secret = base64.b64decode(self.mac_secret_b64)
        except Exception:
            return False
        digest = hmac.new(secret, body, hashlib.sha256).hexdigest()
        expected = f"hmac-sha256={digest}"
        return hmac.compare_digest(expected, signature_header)

    # ---------- payload pull ----------
    async def fetch_payloads(self) -> List[Dict[str, Any]]:
        if not self.webhook_id:
            return []
        collected: List[Dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for _ in range(5):  # safety cap
                r = await client.get(
                    f"{AIRTABLE_API}/bases/{self.base_id}/webhooks/{self.webhook_id}/payloads",
                    headers=self._headers(),
                    params={"cursor": self.cursor},
                )
                if r.status_code == 404:
                    log.warning("Webhook %s vanished — re-registering", self.webhook_id)
                    await self.ensure_registered()
                    return collected
                r.raise_for_status()
                data = r.json()
                collected.extend(data.get("payloads", []) or [])
                self.cursor = int(data.get("cursor") or self.cursor)
                if not data.get("mightHaveMore"):
                    break
        return collected

    # ---------- SSE broadcaster ----------
    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=32)
        async with self._subs_lock:
            self._subscribers.add(q)
        log.debug("SSE subscriber added — total=%d", len(self._subscribers))
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        async with self._subs_lock:
            self._subscribers.discard(q)

    async def broadcast(self, event: Dict[str, Any]) -> None:
        async with self._subs_lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # subscriber is slow — drop this event for them, keep others.
                pass


_manager: Optional[AirtableWebhookManager] = None


def get_webhook_manager() -> Optional[AirtableWebhookManager]:
    return _manager


async def init_webhook_manager() -> Optional[AirtableWebhookManager]:
    """Called from FastAPI lifespan startup. Idempotent."""
    global _manager
    if _manager is not None:
        return _manager
    if os.environ.get("AIRTABLE_WEBHOOK_ENABLED", "").lower() != "true":
        return None
    api_key = os.environ.get("AIRTABLE_API_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    table_id = os.environ.get("AIRTABLE_LEADS_TABLE_ID")
    public_url = os.environ.get("PUBLIC_BACKEND_URL")
    if not (api_key and base_id and table_id and public_url):
        log.warning("Webhook not initialized — missing env "
                    "(AIRTABLE_LEADS_TABLE_ID / PUBLIC_BACKEND_URL required)")
        return None
    mgr = AirtableWebhookManager(
        api_key=api_key, base_id=base_id, table_id=table_id, public_url=public_url,
    )
    try:
        await mgr.ensure_registered()
    except AirtableWebhookManager.MissingWebhookScope as e:
        # Clean, single-line warning. The rest of the app runs perfectly
        # without live push — the frontend falls back to polling.
        log.warning("Live push disabled: %s", e)
        return None
    except Exception:
        log.exception("Webhook registration failed at startup")
        return None
    _manager = mgr
    return _manager


async def shutdown_webhook_manager() -> None:
    global _manager
    if _manager is not None:
        await _manager.unregister()
        _manager = None
