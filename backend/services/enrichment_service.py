"""
AI Contact Enrichment — Gemini + Google Search grounding.

Fills missing `Contact phone` / `Contact email` on Airtable Leads that have
neither on file. Only manual — runs when Ryan taps "Enrich now" in Settings.

Rules:
  • Target only leads missing BOTH phone AND email (and not closed / blocked).
  • Use Gemini 2.5 Flash with the built-in `googleSearch` tool (verifiable,
    grounded output). Never fabricate — the prompt forbids guessing.
  • If the lead is 5+ days old (based on Airtable createdTime) AND the sweep
    still turned up nothing, soft-archive it by setting
    Outreach status = "Archived — no contact found".
  • Writes go through AirtableOpportunityService.update_fields so the
    EDITABLE_FIELDS allowlist is respected.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("bloodhound.enrichment")

CLOSED_STATUSES = {"Won", "Lost", "Disqualified"}
BLOCKED_OUTREACH = {"do not contact", "not interested", "archived"}
SOFT_ARCHIVE_VALUE = "Archived — no contact found"
STALE_DAYS = 5


def _has_phone(opp: Dict[str, Any]) -> bool:
    for key in ("phone", "phone_alt", "phone_number"):
        v = opp.get(key)
        if v and len(str(v).strip()) >= 7:
            return True
    return False


def _has_email(opp: Dict[str, Any]) -> bool:
    for key in ("email", "email_alt"):
        v = opp.get(key)
        if v and "@" in str(v) and "." in str(v).split("@")[-1]:
            return True
    return False


def _is_blocked(opp: Dict[str, Any]) -> bool:
    status = str(opp.get("status") or "").strip()
    if status in CLOSED_STATUSES:
        return True
    for src in (opp.get("outreach_status"), opp.get("approval_status")):
        if not src:
            continue
        s = str(src).lower()
        if any(tok in s for tok in BLOCKED_OUTREACH):
            return True
    return False


def _parse_dt(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return None


def _is_stale(opp: Dict[str, Any]) -> bool:
    created = _parse_dt(opp.get("created_time"))
    if not created:
        return False
    age = datetime.now(timezone.utc) - created
    return age.days >= STALE_DAYS


PHONE_RE = re.compile(r"[+\d][\d\-\.\s\(\)]{6,}\d")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
JSON_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def _clean_phone(v: Any) -> Optional[str]:
    if not v or str(v).lower() in ("null", "none", ""):
        return None
    m = PHONE_RE.search(str(v))
    if not m:
        return None
    raw = m.group(0)
    digits = re.sub(r"\D", "", raw)
    return digits if len(digits) >= 10 else None


def _clean_email(v: Any) -> Optional[str]:
    if not v or str(v).lower() in ("null", "none", ""):
        return None
    m = EMAIL_RE.search(str(v))
    return m.group(0).lower() if m else None


def _clean_url(v: Any) -> Optional[str]:
    if not v or str(v).lower() in ("null", "none", ""):
        return None
    s = str(v).strip()
    return s if s.startswith(("http://", "https://")) else None


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Pull the last balanced JSON object from a mixed prose+JSON response."""
    if not text:
        return None
    # Try direct parse first
    stripped = text.strip().strip("`")
    try:
        return json.loads(stripped)
    except Exception:
        pass
    # Then find every {...} candidate and try the last one first
    candidates = JSON_RE.findall(text)
    for cand in reversed(candidates):
        try:
            return json.loads(cand)
        except Exception:
            continue
    return None


def _build_query(opp: Dict[str, Any]) -> str:
    """Build a compact search prompt for the LLM using every identity clue we have."""
    parts: List[str] = []
    for key, label in (
        ("name", "Business/lead name"),
        ("company", "Company"),
        ("decision_maker", "Owner or contact"),
        ("project_address", "Address"),
        ("city", "City"),
        ("project_type", "What they do"),
        ("permit_description", "Recent activity"),
    ):
        v = opp.get(key)
        if v:
            parts.append(f"{label}: {v}")
    return "\n".join(parts) if parts else "Unnamed lead"


class EnrichmentService:
    """Manual enrichment sweep. Only runs when explicitly kicked off."""

    def __init__(self, api_key: str, airtable_service, model: str = "gemini-2.5-flash"):
        self._key = api_key
        self._airtable = airtable_service
        self._model = model
        self._running = False
        self._lock = asyncio.Lock()
        self._last_run: Optional[Dict[str, Any]] = None
        # Cap per sweep so a single click can't hammer the API.
        self._max_targets = 15

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "last_run": self._last_run,
            "model": self._model,
            "stale_days": STALE_DAYS,
            "max_per_sweep": self._max_targets,
        }

    async def run_sweep(self) -> Dict[str, Any]:
        if self._running:
            return {"error": "already_running", **self.status()}
        async with self._lock:
            self._running = True
            started = datetime.now(timezone.utc)
            scanned = 0
            enriched = 0
            archived = 0
            failed = 0
            errors: List[str] = []
            try:
                all_ops = self._airtable.all() if hasattr(self._airtable, "all") else []
                targets = [
                    o for o in all_ops
                    if not _has_phone(o) and not _has_email(o) and not _is_blocked(o)
                ]
                # Prefer freshest first — older leads are more likely already worked.
                targets.sort(key=lambda o: o.get("created_time") or "", reverse=True)
                targets = targets[: self._max_targets]

                for opp in targets:
                    scanned += 1
                    try:
                        result = await self._enrich_one(opp)
                        if result.get("phone") or result.get("email"):
                            enriched += 1
                        elif _is_stale(opp):
                            try:
                                self._airtable.update_fields(
                                    opp["id"],
                                    {"outreach_status": SOFT_ARCHIVE_VALUE},
                                )
                                archived += 1
                            except Exception as ae:
                                failed += 1
                                errors.append(f"{opp.get('id')}: archive failed — {ae}")
                    except Exception as e:  # noqa: BLE001
                        failed += 1
                        errors.append(f"{opp.get('id')}: {e}")[:180] if False else errors.append(f"{opp.get('id')}: {str(e)[:140]}")

                finished = datetime.now(timezone.utc)
                self._last_run = {
                    "started_at": started.isoformat(),
                    "finished_at": finished.isoformat(),
                    "duration_seconds": round((finished - started).total_seconds(), 1),
                    "scanned": scanned,
                    "enriched": enriched,
                    "archived": archived,
                    "failed": failed,
                    "errors": errors[:5],
                }
                log.info(
                    "enrichment: sweep done · scanned=%d enriched=%d archived=%d failed=%d",
                    scanned, enriched, archived, failed,
                )
                return self._last_run
            finally:
                self._running = False

    async def _enrich_one(self, opp: Dict[str, Any]) -> Dict[str, Any]:
        # Import lazily so the module still loads if emergentintegrations is absent.
        from emergentintegrations.llm.chat import (
            LlmChat,
            UserMessage,
            TextDelta,
            StreamDone,
        )

        query = _build_query(opp)
        session_id = f"enrich-{opp.get('id')}-{int(datetime.now(timezone.utc).timestamp())}"
        chat = (
            LlmChat(
                api_key=self._key,
                session_id=session_id,
                system_message=(
                    "You extract verifiable public business contact information. "
                    "Use Google Search results only. Never guess or fabricate. "
                    "If a value is not clearly supported by a public source, return null."
                ),
            )
            .with_model("gemini", self._model)
            .with_tools([{"googleSearch": {}}])
        )

        prompt = f"""Find the current public business phone number and email address for this lead.

{query}

Rules:
- Use only verifiable public sources (their own website, licensing boards,
  verified business directories). Do NOT use random third-party listings.
- Do NOT guess. If you can't find a value with a clear source, return null.
- Return ONLY a compact JSON object on the last line, no markdown fences,
  no explanation:
{{"phone": "<10-digit US phone or null>", "email": "<email or null>", "website": "<https url or null>", "source_url": "<url where you found it or null>"}}
"""
        text = ""
        try:
            async for ev in chat.stream_message(UserMessage(text=prompt)):
                if isinstance(ev, TextDelta):
                    text += ev.content or ""
                elif isinstance(ev, StreamDone):
                    break
        except Exception as e:  # noqa: BLE001
            log.warning("enrichment: LLM error for %s: %s", opp.get("id"), e)
            return {}

        parsed = _extract_json(text) or {}
        phone = _clean_phone(parsed.get("phone"))
        email = _clean_email(parsed.get("email"))
        website = _clean_url(parsed.get("website"))

        updates: Dict[str, Any] = {}
        if phone:
            updates["phone"] = phone
        if email:
            updates["email"] = email
        if website and not opp.get("website"):
            updates["website"] = website

        if updates:
            try:
                self._airtable.update_fields(opp["id"], updates)
                log.info("enrichment: %s → wrote %s", opp.get("id"), list(updates.keys()))
            except Exception as e:  # noqa: BLE001
                log.warning("enrichment: write failed for %s: %s", opp.get("id"), e)
                return {}
        return {"phone": phone, "email": email, "website": website}


_singleton: Optional[EnrichmentService] = None


def get_enrichment_service():
    global _singleton
    if _singleton is not None:
        return _singleton
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        log.warning("enrichment: EMERGENT_LLM_KEY not set — service disabled")
        return None
    from services.opportunity_service import get_opportunity_service
    svc = get_opportunity_service()
    if not svc or svc.backend_name != "airtable":
        log.warning("enrichment: Airtable backend required — service disabled")
        return None
    _singleton = EnrichmentService(api_key=api_key, airtable_service=svc)
    return _singleton


def reset_enrichment_service():
    global _singleton
    _singleton = None
