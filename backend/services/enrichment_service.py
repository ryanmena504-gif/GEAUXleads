"""
AI Contact Enrichment — Gemini + Google Search grounding.

Fills missing *business* Contact phone / Contact email on Airtable Leads that
have neither on file. Manual only — runs when Ryan taps "Enrich now" in
Settings or "Find public business contact" on a lead's detail page.

Rules (final, 2026-02-11):
  • Target only leads missing BOTH phone AND email that are still active
    (not Won/Lost/Disqualified, not Do Not Contact, not Not Interested).
  • Use Gemini 2.5 Flash with the built-in `googleSearch` tool. Verified
    public BUSINESS or PROFESSIONAL sources only — homeowner / private-owner /
    permit-address contacts are explicitly forbidden.
  • The model returns one of three outcomes:
        contact_found                 — phone or email confirmed
        no_public_business_contact    — nothing found from public sources
        needs_review                  — ambiguous / conflicting sources
  • Records without a hit are NEVER archived, hidden, or retired. Instead
    we write:
        Notes         ← "No public business contact found yet · checked YYYY-MM-DD"
        Next followup ← today + 30 days
    so Ryan can see the state at a glance and manually retry later.
  • SMS Permission is never touched. Outreach sent / Conversation started /
    Message sent date / Reply flags are never touched by enrichment.
  • Writes go through AirtableOpportunityService.update_fields so the
    EDITABLE_FIELDS allowlist is respected.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger("bloodhound.enrichment")

CLOSED_STATUSES = {"Won", "Lost", "Disqualified"}
BLOCKED_OUTREACH = {"do not contact", "not interested"}
RECHECK_DAYS = 30
NO_CONTACT_NOTE_PREFIX = "No public business contact found yet"


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
    if not text:
        return None
    stripped = text.strip().strip("`")
    try:
        return json.loads(stripped)
    except Exception:
        pass
    candidates = JSON_RE.findall(text)
    for cand in reversed(candidates):
        try:
            return json.loads(cand)
        except Exception:
            continue
    return None


def _build_query(opp: Dict[str, Any]) -> str:
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


def _no_contact_note(existing: Any) -> str:
    """Append (or set) a plain-English note that this lead has been checked
    and no public business contact was found yet. Preserves any prior notes."""
    today = datetime.now(timezone.utc).date().isoformat()
    line = f"{NO_CONTACT_NOTE_PREFIX} · checked {today}"
    prior = str(existing or "").strip()
    if not prior:
        return line
    # Avoid duplicating the same message on repeat sweeps.
    if NO_CONTACT_NOTE_PREFIX in prior:
        # Replace the earlier "checked YYYY-MM-DD" fragment.
        prior = re.sub(
            rf"{re.escape(NO_CONTACT_NOTE_PREFIX)}[^\n]*",
            line,
            prior,
            count=1,
        )
        return prior
    return f"{prior}\n{line}"


def _recheck_date() -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=RECHECK_DAYS)).isoformat()


class EnrichmentService:
    """Manual enrichment sweep. Only runs when explicitly kicked off."""

    def __init__(self, api_key: str, airtable_service, model: str = "gemini-2.5-flash"):
        self._key = api_key
        self._airtable = airtable_service
        self._model = model
        self._running = False
        self._lock = asyncio.Lock()
        self._last_run: Optional[Dict[str, Any]] = None
        self._max_targets = 15

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "last_run": self._last_run,
            "model": self._model,
            "recheck_days": RECHECK_DAYS,
            "max_per_sweep": self._max_targets,
        }

    async def enrich_lead(self, opp_id: str) -> Dict[str, Any]:
        """Run enrichment on a single lead. Returns the outcome dict plus the
        updated opportunity DTO. Never runs while a full sweep is in flight."""
        if self._running:
            return {"error": "sweep_in_progress"}
        if not hasattr(self._airtable, "get"):
            return {"error": "airtable_unavailable"}
        opp = self._airtable.get(opp_id)
        if not opp:
            return {"error": "not_found"}
        if _is_blocked(opp):
            return {"error": "blocked", "opportunity": opp}
        result = await self._enrich_one(opp)
        updated = self._airtable.get(opp_id) or opp
        return {"result": result, "opportunity": updated}

    async def run_sweep(self) -> Dict[str, Any]:
        if self._running:
            return {"error": "already_running", **self.status()}
        async with self._lock:
            self._running = True
            started = datetime.now(timezone.utc)
            scanned = 0
            contact_found = 0
            no_contact = 0
            needs_review = 0
            failed = 0
            errors: List[str] = []
            try:
                all_ops = self._airtable.all() if hasattr(self._airtable, "all") else []
                targets = [
                    o for o in all_ops
                    if not _has_phone(o) and not _has_email(o) and not _is_blocked(o)
                ]
                targets.sort(key=lambda o: o.get("created_time") or "", reverse=True)
                targets = targets[: self._max_targets]

                for opp in targets:
                    scanned += 1
                    try:
                        result = await self._enrich_one(opp)
                        outcome = result.get("outcome")
                        if outcome == "contact_found":
                            contact_found += 1
                        elif outcome == "needs_review":
                            needs_review += 1
                        else:
                            no_contact += 1
                    except Exception as e:  # noqa: BLE001
                        failed += 1
                        errors.append(f"{opp.get('id')}: {str(e)[:140]}")

                finished = datetime.now(timezone.utc)
                self._last_run = {
                    "started_at": started.isoformat(),
                    "finished_at": finished.isoformat(),
                    "duration_seconds": round((finished - started).total_seconds(), 1),
                    "scanned": scanned,
                    "contact_found": contact_found,
                    "no_public_business_contact": no_contact,
                    "needs_review": needs_review,
                    "failed": failed,
                    "errors": errors[:5],
                }
                log.info(
                    "enrichment: sweep done · scanned=%d found=%d no_contact=%d review=%d failed=%d",
                    scanned, contact_found, no_contact, needs_review, failed,
                )
                return self._last_run
            finally:
                self._running = False

    async def _enrich_one(self, opp: Dict[str, Any]) -> Dict[str, Any]:
        from emergentintegrations.llm.chat import (
            LlmChat,
            UserMessage,
            TextDelta,
            StreamDone,
        )

        query = _build_query(opp)
        session_id = f"enrich-{opp.get('id')}-{int(datetime.now(timezone.utc).timestamp())}"
        system_message = (
            "You extract verifiable public BUSINESS or PROFESSIONAL contact "
            "information for a contractor's lead pipeline. Use Google Search "
            "results only. HARD RULES:\n"
            "  • Never return a private homeowner, permit-owner, resident, "
            "or personal-cell contact. Only public business or professional "
            "channels: company website contact page, business licensing "
            "records, public business directories (e.g. state contractor "
            "board, chamber of commerce, verified LinkedIn Company page).\n"
            "  • Never guess or fabricate. If not clearly stated on a public "
            "source, do NOT include the value.\n"
            "  • If the lead looks like an individual homeowner (residential "
            "permit, no business name, no company), return outcome "
            "'no_public_business_contact'.\n"
            "  • If two public sources conflict, return outcome 'needs_review'.\n"
        )
        chat = (
            LlmChat(
                api_key=self._key,
                session_id=session_id,
                system_message=system_message,
            )
            .with_model("gemini", self._model)
            .with_tools([{"googleSearch": {}}])
        )

        prompt = f"""Find the current public BUSINESS phone number or email address for this lead.

{query}

Rules:
- Only use verifiable public business sources (company website, licensing
  boards, verified directories). NO homeowner, resident, or private
  numbers. NO permit-address personal cells.
- Do NOT guess. If you can't find a value with a clear public source,
  return outcome "no_public_business_contact".
- If sources disagree, return outcome "needs_review".
- Return ONLY a compact JSON object on the last line, no markdown, no
  explanation:
{{"outcome": "contact_found" | "no_public_business_contact" | "needs_review",
  "phone": "<10-digit US business phone or null>",
  "email": "<business email or null>",
  "website": "<https url or null>",
  "source_url": "<url where the value was found or null>",
  "reason": "<one short sentence why this contact is business-relevant, or empty>"}}
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
            return {"outcome": "needs_review", "error": str(e)[:120]}

        parsed = _extract_json(text) or {}
        outcome = (parsed.get("outcome") or "").strip().lower()
        phone = _clean_phone(parsed.get("phone"))
        email = _clean_email(parsed.get("email"))
        website = _clean_url(parsed.get("website"))
        source_url = _clean_url(parsed.get("source_url"))
        reason = (parsed.get("reason") or "").strip()[:220]

        # Normalize the outcome enum from the LLM's response.
        if outcome not in ("contact_found", "no_public_business_contact", "needs_review"):
            outcome = "contact_found" if (phone or email) else "no_public_business_contact"

        if outcome == "contact_found" and (phone or email):
            updates: Dict[str, Any] = {}
            if phone:
                updates["phone"] = phone
            if email:
                updates["email"] = email
            if website and not opp.get("website"):
                updates["website"] = website
            # Notes: append the source + reason so Ryan can trace where this
            # came from. Never overwrite prior notes silently.
            note_line = f"Enrichment found business contact · {datetime.now(timezone.utc).date().isoformat()}"
            if source_url:
                note_line += f" · source {source_url}"
            if reason:
                note_line += f" · {reason}"
            prior = str(opp.get("notes") or "").strip()
            updates["notes"] = f"{prior}\n{note_line}".strip() if prior else note_line
            try:
                self._airtable.update_fields(opp["id"], updates)
                log.info("enrichment: %s → wrote %s", opp.get("id"), sorted(updates.keys()))
            except Exception as e:  # noqa: BLE001
                log.warning("enrichment: write failed for %s: %s", opp.get("id"), e)
                return {"outcome": "needs_review", "error": str(e)[:120]}
            return {
                "outcome": "contact_found",
                "phone": phone,
                "email": email,
                "website": website,
                "source_url": source_url,
                "reason": reason,
            }

        # No hit or needs review — keep the record in the pool, mark the
        # date checked and the next recheck date. Never archive.
        updates = {
            "notes": _no_contact_note(opp.get("notes")),
            "next_follow_up": _recheck_date(),
        }
        try:
            self._airtable.update_fields(opp["id"], updates)
        except Exception as e:  # noqa: BLE001
            log.warning("enrichment: recheck-tag write failed for %s: %s", opp.get("id"), e)
        return {
            "outcome": outcome,
            "phone": None,
            "email": None,
            "website": None,
            "source_url": source_url,
            "reason": reason,
        }


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
