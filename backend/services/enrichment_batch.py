"""Capped contact-research batch.

One Perplexity call per lead, then at most one OpenAI draft when that
call makes the lead Contact Ready. A paid call that errors is not
retried. After a few failures in a row the batch stops so an outage
cannot walk the whole queue.

The daily cap and the "skip if checked recently" window are env vars.
Manual Find contact passes force=True and ignores both.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from services.field_norm import resolved_phone
from services.contact_research import (
    build_failure_updates,
    build_research_updates,
    checked_today,
    draft_field_updates,
    enrichment_skip_reason,
    has_draft,
    today_iso,
)
from services.draft_safety import looks_like_ai_prompt

log = logging.getLogger("bloodhound.enrichment")

_batch_lock = asyncio.Lock()
_inflight: Set[str] = set()

ResearchFn = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]
UpdateFn = Callable[[str, Dict[str, Any]], Awaitable[Any]]
DraftFn = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


def _env_int(name: str, default: int, low: int, high: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(low, min(high, value))


def daily_cap() -> int:
    """How many leads one day of automatic research may touch. 0 pauses it."""
    return _env_int("ENRICHMENT_DAILY_CAP", 10, 0, 100)


def recheck_days() -> int:
    return _env_int("ENRICHMENT_RECHECK_DAYS", 14, 1, 90)


def max_consecutive_failures() -> int:
    return _env_int("ENRICHMENT_MAX_CONSECUTIVE_FAILURES", 3, 1, 10)


def _sort_key(opp: Dict[str, Any]):
    has_address = 0 if (opp.get("project_address") or "").strip() else 1
    days = -(opp.get("days_on_table") or 0)
    return (has_address, days, str(opp.get("id") or ""))


def select_enrichment_candidates(
    leads: List[Dict[str, Any]],
    *,
    today: str,
    recheck_days_window: int,
    cap: int,
    seen: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Who the batch would research, without calling anything paid."""
    spent = sum(1 for lead in leads if checked_today(lead, today))
    remaining = max(0, cap - spent)
    seen = seen or set()
    chosen = []
    skipped = []
    seen_ids = set(seen)
    ordered = sorted(leads, key=_sort_key)
    for opp in ordered:
        oid = str(opp.get("id") or "")
        if not oid or oid in seen_ids:
            continue
        reason = enrichment_skip_reason(
            opp, today=today, recheck_days=recheck_days_window, force=False
        )
        if reason:
            skipped.append({"id": oid, "reason": reason})
            continue
        seen_ids.add(oid)
        chosen.append(opp)
        if len(chosen) >= remaining:
            break
    return {
        "cap": cap,
        "already_checked_today": spent,
        "remaining": remaining,
        "candidates": [
            {"id": o.get("id"), "name": o.get("name")} for o in chosen
        ],
        "candidate_leads": chosen,
        "skipped_sample": skipped[:20],
    }


async def _persist(update: UpdateFn, opp_id: str, updates: Dict[str, Any]) -> None:
    """Write notes and contact fields first, then the select fields.

    A select value Airtable has never seen ("Research failed") must not
    throw away the note and the checked date that stop a re-run.
    """
    selects = {}
    rest = {}
    for key, value in updates.items():
        if key in {"enrichment_status", "contact_readiness", "contact_confidence", "first_contact_channel"}:
            selects[key] = value
        else:
            rest[key] = value
    if rest:
        await update(opp_id, rest)
    if not selects:
        return
    try:
        await update(opp_id, selects)
    except Exception:
        log.exception("enrichment status write failed for %s — note and date were kept", opp_id)


def _draft_channel(opp: Dict[str, Any], updates: Dict[str, Any]) -> str:
    phone = updates.get("phone") or resolved_phone(opp)
    return "Text" if phone else "Email"


async def run_enrichment_batch(
    leads: List[Dict[str, Any]],
    *,
    research: ResearchFn,
    update: UpdateFn,
    draft: Optional[DraftFn] = None,
    today: Optional[str] = None,
    cap: Optional[int] = None,
    recheck_window: Optional[int] = None,
    failure_limit: Optional[int] = None,
    dry_run: bool = False,
    seen: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Research eligible leads until the cap or the failure streak is hit.

    `research` is called at most once per lead. A raise is a failure, not
    a cue to call it again.
    """
    today = today or today_iso()
    cap = daily_cap() if cap is None else cap
    window = recheck_days() if recheck_window is None else recheck_window
    limit = max_consecutive_failures() if failure_limit is None else failure_limit
    plan = select_enrichment_candidates(
        leads, today=today, recheck_days_window=window, cap=cap, seen=seen
    )
    summary: Dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "cap": plan["cap"],
        "already_checked_today": plan["already_checked_today"],
        "remaining": plan["remaining"],
        "candidates": len(plan["candidates"]),
        "processed": 0,
        "contact_found": 0,
        "no_contact": 0,
        "failed": 0,
        "drafts": 0,
        "draft_failures": 0,
        "drafts_unconfigured": False,
        "stopped_early": False,
        "stop_reason": None,
        "results": [],
    }
    if dry_run:
        summary["results"] = plan["candidates"]
        return summary

    streak = 0
    drafts_off = False
    for opp in plan["candidate_leads"]:
        if streak >= limit:
            summary["stopped_early"] = True
            summary["stop_reason"] = f"{limit} paid calls failed in a row"
            break
        oid = str(opp.get("id") or "")
        if seen is not None:
            seen.add(oid)
        try:
            parsed = await research(opp)
        except Exception as exc:
            streak += 1
            summary["failed"] += 1
            summary["processed"] += 1
            built = build_failure_updates(opp, str(exc), today=today)
            try:
                await _persist(update, oid, built["updates"])
            except Exception:
                log.exception("enrichment failure-note write failed for %s", oid)
            summary["results"].append({
                "id": oid,
                "name": opp.get("name"),
                "outcome": "failed",
                "error": str(exc)[:240],
            })
            log.warning("contact research failed for %s (%s)", oid, type(exc).__name__)
            continue

        built = build_research_updates(opp, parsed or {}, today=today, force=False)
        try:
            await _persist(update, oid, built["updates"])
        except Exception as exc:
            streak += 1
            summary["failed"] += 1
            summary["processed"] += 1
            summary["results"].append({
                "id": oid,
                "name": opp.get("name"),
                "outcome": "failed",
                "error": f"save failed: {exc}"[:240],
            })
            continue

        summary["processed"] += 1
        outcome = built["outcome"]
        if outcome == "contact_found":
            summary["contact_found"] += 1
        else:
            summary["no_contact"] += 1
        row = {"id": oid, "name": opp.get("name"), "outcome": outcome}
        summary["results"].append(row)

        merged = {**opp, **built["updates"]}
        needs_draft = (
            built["became_contact_ready"]
            and not drafts_off
            and draft is not None
            and not has_draft(merged)
        )
        if not needs_draft:
            # Research succeeded. A skipped draft is not a paid-call failure,
            # so the consecutive-failure streak starts over.
            streak = 0
            continue
        try:
            drafted = await draft(merged)
        except RuntimeError as exc:
            if "not configured" in str(exc).lower():
                drafts_off = True
                summary["drafts_unconfigured"] = True
                streak = 0
                log.warning("outreach drafts skipped — OpenAI is not configured")
                continue
            streak += 1
            summary["draft_failures"] += 1
            log.warning("draft failed for %s (%s)", oid, type(exc).__name__)
            continue
        except Exception as exc:
            streak += 1
            summary["draft_failures"] += 1
            log.warning("draft failed for %s (%s)", oid, type(exc).__name__)
            continue

        text = (drafted or {}).get("draft") or ""
        if text.upper().startswith("FLAG:") or looks_like_ai_prompt(text)[0]:
            log.info("draft for %s was not stored (safety)", oid)
            streak = 0
            continue
        channel = _draft_channel(opp, built["updates"])
        fields = draft_field_updates(
            text,
            (drafted or {}).get("subject") or "outreach draft",
            (drafted or {}).get("recipe_text") or "",
            generated_at=datetime.now(timezone.utc).isoformat(),
            channel=channel,
        )
        try:
            await _persist(update, oid, fields)
            summary["drafts"] += 1
            row["drafted"] = True
        except Exception:
            summary["draft_failures"] += 1
            log.exception("draft save failed for %s", oid)
        streak = 0

    if streak >= limit and not summary["stopped_early"]:
        summary["stopped_early"] = True
        summary["stop_reason"] = f"{limit} paid calls failed in a row"
    return summary


async def enrich_and_persist(
    svc,
    opp: Dict[str, Any],
    *,
    force: bool = False,
    seen: Optional[Set[str]] = None,
    research: Optional[ResearchFn] = None,
    draft: Optional[DraftFn] = None,
) -> Dict[str, Any]:
    """One lead: a single contact lookup, a write, and a draft when it lands.

    Used by the Find contact button (force=True) and by Fresh Intel's
    auto-enhance hook (force=False). Does not retry a failed call.
    """
    oid = str(opp.get("id") or "")
    if not oid:
        return {"outcome": "skipped", "reason": "missing id"}
    if oid in _inflight:
        return {"outcome": "skipped", "reason": "already running"}

    today = today_iso()
    # force=True is the Find contact button: it ignores the daily cap and
    # the recent-check window, but it still refuses a lead with no name
    # and no address, because that call cannot find anything.
    reason = enrichment_skip_reason(
        opp, today=today, recheck_days=recheck_days(), force=force
    )
    if reason:
        if seen is not None and not force:
            seen.add(oid)
        return {"outcome": "skipped", "reason": reason}

    _inflight.add(oid)
    try:
        if seen is not None:
            seen.add(oid)
        if research is None:
            from services.contact_finder_service import run_contact_finder
            research = run_contact_finder
        try:
            parsed = await research(opp)
        except Exception as exc:
            built = build_failure_updates(opp, str(exc), today=today)
            await _persist(_svc_update(svc), oid, built["updates"])
            log.warning("contact research failed for %s (%s)", oid, type(exc).__name__)
            return {"outcome": "failed", "error": str(exc)[:240], "id": oid}

        built = build_research_updates(opp, parsed or {}, today=today, force=force)
        await _persist(_svc_update(svc), oid, built["updates"])
        result = {
            "outcome": built["outcome"],
            "id": oid,
            "became_contact_ready": built["became_contact_ready"],
            "drafted": False,
        }
        if not built["became_contact_ready"]:
            return result
        merged = {**opp, **built["updates"]}
        if has_draft(merged):
            return result
        if draft is None:
            draft = _default_draft
        try:
            drafted = await draft(merged)
        except RuntimeError as exc:
            if "not configured" in str(exc).lower():
                result["drafts_unconfigured"] = True
                return result
            log.warning("draft failed for %s (%s)", oid, type(exc).__name__)
            result["draft_error"] = str(exc)[:240]
            return result
        except Exception as exc:
            log.warning("draft failed for %s (%s)", oid, type(exc).__name__)
            result["draft_error"] = str(exc)[:240]
            return result
        text = (drafted or {}).get("draft") or ""
        if not text or text.upper().startswith("FLAG:") or looks_like_ai_prompt(text)[0]:
            return result
        fields = draft_field_updates(
            text,
            (drafted or {}).get("subject") or "outreach draft",
            (drafted or {}).get("recipe_text") or "",
            generated_at=datetime.now(timezone.utc).isoformat(),
            channel=_draft_channel(opp, built["updates"]),
        )
        await _persist(_svc_update(svc), oid, fields)
        result["drafted"] = True
        return result
    finally:
        _inflight.discard(oid)


def _svc_update(svc):
    async def _update(opp_id: str, fields: Dict[str, Any]):
        fn = svc.update_fields
        if asyncio.iscoroutinefunction(fn):
            return await fn(opp_id, fields)
        return await asyncio.to_thread(fn, opp_id, fields)

    return _update


async def _default_draft(opp: Dict[str, Any]) -> Dict[str, Any]:
    from services.outreach_draft_service import generate_draft, recipe_to_field

    result = await generate_draft(opp)
    result["recipe_text"] = recipe_to_field(result.get("recipe") or {})
    return result


async def _load_leads(svc) -> List[Dict[str, Any]]:
    if asyncio.iscoroutinefunction(svc.list):
        listed = await svc.list()
    else:
        listed = await asyncio.to_thread(svc.list)
    return list(listed or [])


async def run_for_service(
    svc,
    *,
    dry_run: bool = False,
    seen: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Batch entry used by the admin endpoint, the scheduler, and Fresh Intel.

    A second overlapping run returns immediately and does not spend credits.
    """
    if _batch_lock.locked() and not dry_run:
        return {"ok": False, "skipped": "already running"}
    async with _batch_lock:
        leads = await _load_leads(svc)

        async def _update(opp_id: str, fields: Dict[str, Any]):
            return await _svc_update(svc)(opp_id, fields)

        async def _research(opp: Dict[str, Any]):
            from services.contact_finder_service import run_contact_finder
            return await run_contact_finder(opp)

        return await run_enrichment_batch(
            leads,
            research=_research,
            update=_update,
            draft=None if dry_run else _default_draft,
            dry_run=dry_run,
            seen=seen,
        )


