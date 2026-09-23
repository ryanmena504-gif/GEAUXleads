from fastapi import FastAPI, APIRouter, HTTPException, Request, BackgroundTasks, Header
from fastapi.responses import JSONResponse, StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import json
import asyncio
import hmac
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from services.opportunity_service import get_opportunity_service, reset_opportunity_service
from services.leads_service import get_leads_service, reset_leads_service
from services.airtable_service import AirtableWriteError
from services.slack_service import (
    get_slack_alerter,
    is_configured as slack_is_configured,
)
from services.playbook_service import get_playbook_service
from services.draft_service import get_draft_service, REVIEW_STATUSES
from services.handoff_service import get_handoff_service
from services.user_settings_service import get_user_settings_service, DEFAULTS as USER_SETTINGS_DEFAULTS
from services.webhook_service import (
    init_webhook_manager,
    shutdown_webhook_manager,
    get_webhook_manager,
)


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup: register the Airtable webhook (idempotent).
    try:
        await init_webhook_manager()
    except Exception:
        logging.getLogger("bloodhound").exception("Webhook init failed at startup")
    # Slack alerter init — logs a one-time warning if webhook URL is absent.
    try:
        get_slack_alerter()
    except Exception:
        logging.getLogger("bloodhound").exception("Slack alerter init failed at startup")
    yield
    # Shutdown: best-effort webhook cleanup.
    try:
        await shutdown_webhook_manager()
    except Exception:
        pass


app = FastAPI(title="GEAUXleads Intelligence API", lifespan=lifespan)
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("bloodhound")


class StatusUpdate(BaseModel):
    status: str


class MissionUpdate(BaseModel):
    daily_mission: str


class ActivityEntry(BaseModel):
    type: str
    note: Optional[str] = None


class FieldUpdate(BaseModel):
    status: Optional[str] = None
    ryans_decision: Optional[str] = None
    next_follow_up: Optional[str] = None
    outcome: Optional[str] = None


class ResultUpdate(BaseModel):
    """A human-confirmed outcome. This never opens or sends a message."""
    event: str
    channel: Optional[str] = None
    note: Optional[str] = None


@api_router.get("/")
async def root():
    return {"service": "GEAUXleads Intelligence API", "status": "online"}


@api_router.get("/health")
async def health():
    svc = get_opportunity_service()
    return {"ok": True, "backend": svc.backend_name, "count": svc.count()}


@api_router.get("/opportunities")
async def list_opportunities(
    source: Optional[str] = None,
    status: Optional[str] = None,
    priority_band: Optional[str] = None,
    daily_mission: Optional[str] = None,
    project_type: Optional[str] = None,
    min_score: Optional[float] = None,
    q: Optional[str] = None,
    lane: Optional[str] = None,
    sort: Optional[str] = "lead_score",
    view: Optional[str] = None,
):
    svc = get_opportunity_service()
    return svc.list(
        source=source,
        status=status,
        priority_band=priority_band,
        daily_mission=daily_mission,
        project_type=project_type,
        min_score=min_score,
        q=q,
        lane=lane,
        sort=sort,
        view=view,
    )


@api_router.get("/opportunities/lanes")
async def lane_breakdown():
    """Counts + pipeline value per lane (market_capture / partner / non_permit)."""
    svc = get_opportunity_service()
    LANES = ("market_capture", "partner", "non_permit")
    LABEL = {"market_capture": "Market Capture", "partner": "Partner Pipeline",
             "non_permit": "Non-Permit Signals"}
    all_ops = svc.all() if hasattr(svc, "all") else []
    out = []
    for lane in LANES:
        rows = [o for o in all_ops if o.get("lane") == lane]
        active = [o for o in rows if o.get("status") not in ("Won", "Lost", "Disqualified")]
        value = sum((o.get("estimated_value") or 0) for o in active)
        scored = [o for o in active if isinstance(o.get("priority_score"), (int, float))]
        scored.sort(key=lambda o: -o["priority_score"])
        out.append({
            "lane": lane,
            "label": LABEL[lane],
            "total": len(rows),
            "active": len(active),
            "pipeline_value": value,
            "top_score": (scored[0].get("priority_score") if scored else None),
        })
    return out


@api_router.get("/opportunities/top-by-lane")
async def top_by_lane(limit: int = 4):
    """Top N per lane, ranked by canonical Lead score."""
    from services.airtable_service import sort_opportunities as _sort_ops
    svc = get_opportunity_service()
    LANES = ("market_capture", "partner", "non_permit")
    all_ops = svc.all() if hasattr(svc, "all") else []
    out = {}
    for lane in LANES:
        rows = [o for o in all_ops
                if o.get("lane") == lane
                and o.get("status") not in ("Won", "Lost", "Disqualified")]
        out[lane] = _sort_ops(rows, mode="lead_score")[:limit]
    return out


@api_router.get("/opportunities/summary")
async def summary():
    svc = get_opportunity_service()
    return svc.summary()


@api_router.get("/opportunities/missions")
async def missions_grouped():
    svc = get_opportunity_service()
    return svc.group_by_mission()


@api_router.get("/opportunities/pipeline")
async def pipeline():
    svc = get_opportunity_service()
    return svc.pipeline_counts()


@api_router.get("/opportunities/recent")
async def recent(limit: int = 10):
    svc = get_opportunity_service()
    return svc.recent(limit=limit)


@api_router.get("/opportunities/top")
async def top(limit: int = 10):
    svc = get_opportunity_service()
    return svc.top(limit=limit)


@api_router.get("/opportunities/{opp_id}")
async def get_opportunity(opp_id: str):
    svc = get_opportunity_service()
    opp = svc.get(opp_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opp


@api_router.patch("/opportunities/{opp_id}/status")
async def update_status(opp_id: str, body: StatusUpdate):
    svc = get_opportunity_service()
    updated = svc.update_status(opp_id, body.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return updated


@api_router.patch("/opportunities/{opp_id}/mission")
async def update_mission(opp_id: str, body: MissionUpdate):
    svc = get_opportunity_service()
    updated = svc.update_mission(opp_id, body.daily_mission)
    if not updated:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return updated


@api_router.post("/opportunities/{opp_id}/activity")
async def add_activity(opp_id: str, body: ActivityEntry):
    svc = get_opportunity_service()
    updated = svc.add_activity(opp_id, body.type, body.note)
    if not updated:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return updated


@api_router.patch("/opportunities/{opp_id}/fields")
async def update_fields(opp_id: str, body: FieldUpdate):
    svc = get_opportunity_service()
    # Accept empty-string values as explicit "clear" intent.
    payload = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if not payload:
        # Silent-ignore: nothing to write, just return current DTO.
        current = svc.get(opp_id)
        if not current:
            raise HTTPException(status_code=404, detail="Opportunity not found")
        return current
    if hasattr(svc, "update_fields"):
        try:
            updated = svc.update_fields(opp_id, payload)
        except AirtableWriteError as e:
            raise HTTPException(status_code=e.status_code, detail=str(e))
    else:
        # Sample backend: apply supported keys one-by-one
        updated = svc.get(opp_id)
        if not updated:
            raise HTTPException(status_code=404, detail="Opportunity not found")
        if "status" in payload:
            updated = svc.update_status(opp_id, payload["status"])
        for k in ("ryans_decision", "next_follow_up", "outcome"):
            if k in payload and updated is not None:
                updated[k] = payload[k]
    if not updated:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return updated


@api_router.post("/opportunities/{opp_id}/result")
async def record_result(opp_id: str, body: ResultUpdate):
    """Persist a result only after Ryan explicitly confirms it in the app."""
    event = (body.event or "").strip().lower()
    channel = (body.channel or "").strip()
    if event not in {"sent", "replied", "estimate_requested", "not_interested", "no_response"}:
        raise HTTPException(status_code=422, detail="Unknown result")
    if channel and channel not in {"Text", "Email", "Call", "Other"}:
        raise HTTPException(status_code=422, detail="Unknown contact method")

    now = datetime.now(timezone.utc).isoformat()
    updates: Dict[str, Any] = {}
    if event == "sent":
        # Pipeline status must NOT auto-advance on "I sent it".
        updates = {
            "outreach_status": "Sent",
            "outreach_channel": channel or "Other",
            "message_sent_date": now,
            "date_contacted": now,
        }
    elif event == "replied":
        updates = {
            "outreach_status": "Replied",
            "reply_classification": "Needs more information",
            "reply_summary": body.note or "Reply received",
            "date_replied": now,
        }
    elif event == "estimate_requested":
        updates = {
            "outreach_status": "Estimate requested",
            "reply_classification": "Interested",
            "reply_summary": body.note or "Estimate requested",
            "date_replied": now,
        }
    elif event == "not_interested":
        updates = {
            "outreach_status": "Not interested",
            "reply_classification": "Not interested",
            "reply_summary": body.note or "Not interested",
            "date_replied": now,
        }
    elif event == "no_response":
        updates = {"outreach_status": "No response"}

    svc = get_opportunity_service()
    try:
        updated = svc.update_fields(opp_id, updates) if hasattr(svc, "update_fields") else None
    except AirtableWriteError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return updated


@api_router.get("/config")
async def config():
    from services.opportunity_service import get_last_init_error
    svc = get_opportunity_service()
    return {
        "airtable_configured": bool(
            os.environ.get("AIRTABLE_API_KEY")
            and os.environ.get("AIRTABLE_BASE_ID")
            and os.environ.get("AIRTABLE_OPPORTUNITIES_TABLE")
        ),
        "airtable_enabled": os.environ.get("AIRTABLE_ENABLED", "").lower() == "true",
        "backend": svc.backend_name,
        # Reason the Airtable init failed (401, missing table, etc.) — null
        # when Airtable is live or was never attempted.
        "airtable_init_error": get_last_init_error(),
        # Airtable identifiers used only to construct DEEPLINKS in the UI
        # (e.g. "Open in Airtable" jump-links from locked-outreach notices).
        # Not secrets — base + table IDs are visible to any authenticated
        # Airtable user on the base. API key stays server-side.
        "airtable_base_id": os.environ.get("AIRTABLE_BASE_ID") or None,
        "airtable_leads_table_id": os.environ.get("AIRTABLE_LEADS_TABLE_ID") or None,
    }


@api_router.get("/schema")
async def schema():
    svc = get_opportunity_service()
    if hasattr(svc, "schema_report"):
        return svc.schema_report()
    return {"backend": svc.backend_name, "note": "No schema — running on sample data."}


@api_router.get("/cache-status")
async def cache_status():
    svc = get_opportunity_service()
    return svc.cache_status()


@api_router.post("/cache-refresh")
async def cache_refresh():
    svc = get_opportunity_service()
    return svc.force_refresh()


# ---------- Leads / Next Best Action ----------

class LeadAction(BaseModel):
    action: str  # approve (disabled) | hold | skip | do_not_contact
    confirm: Optional[bool] = False


class LeadMessageUpdate(BaseModel):
    message: str


@api_router.get("/leads/next-best-action")
async def leads_next_best_action():
    svc = get_leads_service()
    if not svc:
        return {
            "lead": None,
            "queue": None,
            "note": "Leads service not available — set AIRTABLE_ENABLED=true and ensure the Leads table exists.",
        }
    lead = svc.pick_next_best_action()
    if not lead:
        return {
            "lead": None,
            "queue": svc.queue_stats(),
            "note": "No qualified leads remaining in the queue.",
        }
    return {"lead": lead, "queue": svc.queue_stats()}


@api_router.post("/leads/{lead_id}/action")
async def leads_action(lead_id: str, body: LeadAction):
    action = (body.action or "").lower()
    if action == "approve":
        # GEAUXleads is approval-only. A dashboard approval must never become
        # provider delivery: use the device-native draft handoff instead.
        raise HTTPException(
            status_code=410,
            detail=(
                "Direct email delivery is disabled. Open a device-native draft, "
                "send it yourself, then record the result in GEAUXleads."
            ),
        )

    svc = get_leads_service()
    if not svc:
        raise HTTPException(status_code=503, detail="Leads service not available")
    if svc.get(lead_id) is None:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")
    if action == "hold":
        return svc.hold(lead_id)
    if action == "release_hold":
        if (svc.get(lead_id) or {}).get("hunt_status") != "Paused":
            raise HTTPException(status_code=409, detail="Lead is not on hold (Hunt status is not Paused)")
        return svc.release_hold(lead_id)
    if action == "skip":
        return svc.skip(lead_id)
    if action == "do_not_contact":
        if not body.confirm:
            raise HTTPException(status_code=400,
                                detail="Confirmation required for Do Not Contact")
        return svc.do_not_contact(lead_id)
    raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")


@api_router.patch("/leads/{lead_id}/message")
async def leads_update_message(lead_id: str, body: LeadMessageUpdate):
    svc = get_leads_service()
    if not svc:
        raise HTTPException(status_code=503, detail="Leads service not available")
    updated = svc.update_message(lead_id, body.message)
    if not updated:
        raise HTTPException(status_code=404, detail="Message update failed")
    return updated


@api_router.post("/admin/reload")
async def reload_service():
    reset_opportunity_service()
    reset_leads_service()
    svc = get_opportunity_service()
    get_leads_service()
    return {"ok": True, "backend": svc.backend_name}


# ============================================================================
# Airtable webhook receiver + live SSE stream
# ============================================================================

async def _handle_ping_background():
    """Fetch payloads, invalidate caches, broadcast to SSE subscribers."""
    mgr = get_webhook_manager()
    if not mgr:
        return
    try:
        payloads = await mgr.fetch_payloads()
    except Exception:
        logger.exception("webhook: fetch_payloads failed")
        return
    if not payloads:
        return
    # Invalidate both service caches so the next read fetches fresh data.
    opps = get_opportunity_service()
    if hasattr(opps, "force_refresh"):
        try:
            await asyncio.to_thread(opps.force_refresh)
        except Exception:
            logger.exception("webhook: opps force_refresh failed")
    leads = get_leads_service()
    if leads and hasattr(leads, "_refresh_cache"):
        try:
            await asyncio.to_thread(leads._refresh_cache, True)
        except Exception:
            logger.exception("webhook: leads refresh failed")
    # Summarise the change types for the client.
    changed_records = set()
    for p in payloads:
        for _tbl_id, tbl in (p.get("changedTablesById") or {}).items():
            for rid in (tbl.get("changedRecordsById") or {}):
                changed_records.add(rid)
            for rid in (tbl.get("createdRecordsById") or {}):
                changed_records.add(rid)
    await mgr.broadcast({
        "type": "airtable_change",
        "payload_count": len(payloads),
        "changed_record_ids": sorted(changed_records),
        "at": datetime.now(timezone.utc).isoformat(),
    })
    # Fire Band A Slack alerts (best-effort — never blocks the SSE broadcast).
    try:
        alerter = get_slack_alerter()
        if alerter and slack_is_configured():
            opps_svc = get_opportunity_service()
            band_a = [o for o in opps_svc.all() if o.get("priority_band") == "A"]
            if band_a:
                await alerter.evaluate_and_alert(band_a)
    except Exception:
        logger.exception("webhook: slack alerter failed")


@app.post("/api/airtable/webhook")
async def airtable_webhook_receiver(request: Request):
    mgr = get_webhook_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Webhook manager not initialized")
    body = await request.body()
    signature = request.headers.get("x-airtable-content-mac") or request.headers.get("X-Airtable-Content-MAC")
    if not mgr.verify_signature(body, signature):
        logger.warning("webhook: signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid signature")
    # Airtable expects a fast 200. Do the heavy lift on the event loop.
    asyncio.create_task(_handle_ping_background())
    return {"ok": True}


@api_router.get("/live/stream")
async def live_stream(request: Request):
    """SSE stream that emits an 'update' event whenever Airtable pings us."""
    mgr = get_webhook_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Live stream not available")

    async def event_gen():
        q = await mgr.subscribe()
        try:
            # Initial hello so the client's onopen fires reliably.
            yield "event: ready\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=25.0)
                except asyncio.TimeoutError:
                    # heartbeat keeps proxies from killing the connection
                    yield ": heartbeat\n\n"
                    continue
                yield f"event: update\ndata: {json.dumps(evt)}\n\n"
        finally:
            await mgr.unsubscribe(q)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@api_router.get("/live/status")
async def live_status():
    mgr = get_webhook_manager()
    if not mgr:
        return {"registered": False}
    return {
        "registered": bool(mgr.webhook_id),
        "webhook_id": mgr.webhook_id,
        "table_id": mgr.table_id,
        "notification_url": mgr.notification_url,
        "cursor": mgr.cursor,
        "subscribers": len(mgr._subscribers),
    }


@api_router.post("/live/reregister")
async def live_reregister():
    """Force a fresh webhook registration (rotates the mac secret)."""
    from services.webhook_service import _manager as _cur, init_webhook_manager  # local import to reset singleton
    try:
        if _cur is not None:
            await _cur.unregister()
    except Exception:
        pass
    import services.webhook_service as ws
    ws._manager = None
    mgr = await init_webhook_manager()
    if not mgr:
        raise HTTPException(status_code=500, detail="Re-registration failed")
    return {"ok": True, "webhook_id": mgr.webhook_id}


# ============================================================================
# Slack alerts — status + manual trigger. Webhook URL is NEVER exposed.
# ============================================================================
@api_router.get("/slack/alerts/status")
async def slack_alerts_status():
    """Reports whether Slack alerts are wired up. Does NOT return the URL."""
    alerter = get_slack_alerter()
    configured = slack_is_configured()
    tracked = 0
    last_alert = None
    if alerter and configured:
        try:
            tracked = await alerter._col.count_documents({})
            last = await alerter._col.find_one(sort=[("alert_sent_at", -1)])
            if last:
                last_alert = {
                    "opportunity_id": last.get("opportunity_id"),
                    "alert_sent_at": last.get("alert_sent_at"),
                    "last_alerted_score": last.get("last_alerted_score"),
                    "last_reason": last.get("last_reason"),
                }
        except Exception:
            logger.exception("slack status query failed")
    return {
        "configured": configured,
        "score_delta_threshold": 10.0,
        "tracked_alerts_total": tracked,
        "last_alert": last_alert,
    }


# ============================================================================
# Draft a Note — Message Playbooks (Airtable, read-only) + Outreach Drafts
# (Mongo-backed CRUD) + SMS Draft (Airtable Notes field). DRAFT-ONLY.
# There is no send path in this file — never has been, never will be.
# ============================================================================
@api_router.get("/message-playbooks")
async def list_message_playbooks():
    svc = get_playbook_service()
    if not svc:
        return {"available": False, "playbooks": []}
    playbooks = svc.list()
    safe = [
        {
            "id": p.get("id"),
            "playbook_id": p.get("playbook_id"),
            "name": p.get("name"),
            "audience_type": p.get("audience_type"),
            "audience_slug": p.get("audience_slug"),
            "channel": p.get("channel"),
            "default_subject": p.get("default_subject"),
            "default_draft": p.get("default_draft"),
            "editable_variables": p.get("editable_variables"),
            "voice_rules": p.get("voice_rules"),
            "approval_note": p.get("approval_note"),
        }
        for p in playbooks
    ]
    return {"available": True, "playbooks": safe}


class PlaybookUpdate(BaseModel):
    default_subject: Optional[str] = None
    default_draft: Optional[str] = None


@api_router.patch("/message-playbooks/{playbook_id}")
async def update_message_playbook(playbook_id: str, payload: PlaybookUpdate):
    """Update Default Subject / Default Draft on a playbook record in
    Airtable. Restricted to those two fields — never touches Audience Type,
    Voice Rules, Status, or anything else in the table."""
    svc = get_playbook_service()
    if not svc:
        raise HTTPException(status_code=503, detail="Playbook service unavailable")
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(status_code=422, detail="No editable fields provided")
    try:
        updated = svc.update(playbook_id, patch)
    except Exception:
        raise HTTPException(status_code=502, detail="Airtable update failed")
    if not updated:
        raise HTTPException(status_code=404, detail="Playbook not found")
    return {
        "id": updated.get("id"),
        "playbook_id": updated.get("playbook_id"),
        "name": updated.get("name"),
        "audience_type": updated.get("audience_type"),
        "audience_slug": updated.get("audience_slug"),
        "default_subject": updated.get("default_subject"),
        "default_draft": updated.get("default_draft"),
    }


class DraftCreate(BaseModel):
    opportunity_id: str
    opportunity_name: Optional[str] = None
    selected_playbook: Optional[str] = None
    subject: Optional[str] = ""
    body: Optional[str] = ""
    internal_note: Optional[str] = ""
    review_status: Optional[str] = "Draft"


class DraftUpdate(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None
    internal_note: Optional[str] = None
    selected_playbook: Optional[str] = None
    review_status: Optional[str] = None


@api_router.get("/drafts")
async def list_drafts(opportunity_id: str):
    svc = get_draft_service()
    if not svc:
        return {"available": False, "drafts": []}
    drafts = await svc.list_for_opportunity(opportunity_id)
    return {"available": True, "drafts": drafts}


@api_router.get("/drafts/queue")
async def draft_review_queue(
    status: str = "Ready for Ryan review",
    limit: int = 200,
):
    """List every draft matching the requested review status, newest first.
    Also returns a status breakdown so the UI can show live counts."""
    svc = get_draft_service()
    if not svc:
        return {"available": False, "status": status, "drafts": [], "counts": {}}
    if status not in REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail="Unknown review_status")
    drafts = await svc.list_by_status(status, limit=max(1, min(limit, 500)))
    counts = await svc.counts_by_status()
    return {
        "available": True,
        "status": status,
        "count": len(drafts),
        "counts": counts,
        "drafts": drafts,
    }


@api_router.post("/drafts")
async def create_draft(payload: DraftCreate):
    svc = get_draft_service()
    if not svc:
        raise HTTPException(status_code=503, detail="Draft store unavailable")
    return await svc.create(payload.model_dump())


@api_router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str):
    svc = get_draft_service()
    if not svc:
        raise HTTPException(status_code=503, detail="Draft store unavailable")
    doc = await svc.get(draft_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Draft not found")
    return doc


@api_router.patch("/drafts/{draft_id}")
async def update_draft(draft_id: str, payload: DraftUpdate):
    svc = get_draft_service()
    if not svc:
        raise HTTPException(status_code=503, detail="Draft store unavailable")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    doc = await svc.update(draft_id, updates)
    if not doc:
        raise HTTPException(status_code=404, detail="Draft not found")
    return doc


@api_router.delete("/drafts/{draft_id}")
async def delete_draft(draft_id: str):
    svc = get_draft_service()
    if not svc:
        raise HTTPException(status_code=503, detail="Draft store unavailable")
    ok = await svc.delete(draft_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"ok": True}


# --------------------------------------------------------------------------
# Reserved: previously hosted a POST /opportunities/{id}/sms-draft that wrote
# an SMS draft into Airtable's Notes field. Removed 2026-02-06 in favor of a
# pure client-side iPhone handoff (OpenInMessages) — no backend write, no
# messaging API, no automation. If you're looking for send-anything logic in
# this file, stop looking. There isn't any.
# --------------------------------------------------------------------------


# ============================================================================
# Contact-handoff log — every tap of the Text/Email buttons on any device
# logs ONE event immediately. Because Mail on iPhone / laptop uses whichever
# account is the OS default, we can't observe the actual send — we log the
# INTENT-TO-HANDOFF client-side. No messaging API is called.
# ============================================================================
class HandoffCreate(BaseModel):
    opportunity_id: str
    opportunity_name: Optional[str] = None
    channel: str  # "text" | "email"
    recipient: Optional[str] = None


@api_router.post("/opportunities/{opp_id}/handoff")
async def log_handoff(opp_id: str, payload: HandoffCreate, request: Request):
    svc = get_handoff_service()
    if not svc:
        raise HTTPException(status_code=503, detail="Handoff log unavailable")
    if payload.opportunity_id and payload.opportunity_id != opp_id:
        raise HTTPException(status_code=422, detail="opportunity_id mismatch")
    if payload.channel not in ("text", "email"):
        raise HTTPException(status_code=422, detail="channel must be 'text' or 'email'")
    try:
        rec = await svc.create(
            {
                "opportunity_id": opp_id,
                "opportunity_name": payload.opportunity_name,
                "channel": payload.channel,
                "recipient": payload.recipient,
            },
            user_agent=request.headers.get("user-agent"),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return rec


@api_router.get("/opportunities/{opp_id}/handoffs")
async def list_handoffs_for(opp_id: str, limit: int = 50):
    svc = get_handoff_service()
    if not svc:
        return {"available": False, "handoffs": []}
    handoffs = await svc.list_for_opportunity(opp_id, limit=limit)
    return {"available": True, "handoffs": handoffs}


@api_router.get("/handoffs/recent")
async def list_recent_handoffs(limit: int = 100):
    svc = get_handoff_service()
    if not svc:
        return {"available": False, "handoffs": []}
    handoffs = await svc.list_recent(limit=limit)
    return {"available": True, "handoffs": handoffs}


# ============================================================================
# Follow-up sequencing — cross-references the handoff_log with the opportunity
# list to find leads that were touched days ago and never nudged again.
# Owners buy from whoever is still present; this endpoint keeps Ryan present.
# ============================================================================
@api_router.get("/follow-ups/due")
async def follow_ups_due(limit: int = 20):
    """Leads Ryan touched but hasn't nudged recently.

    Buckets (evaluated in order — first match wins):
      • estimate_check  · status = Estimate requested / Estimate sent AND
                          last touch ≥ 7 days ago
      • email_nudge     · last touch was email AND ≥ 5 days ago
      • text_nudge      · last touch was text  AND ≥ 3 days ago
    """
    hsvc = get_handoff_service()
    osvc = get_opportunity_service()
    if not hsvc or not osvc:
        return {"available": False, "items": []}

    from datetime import datetime, timezone as _tz
    now = datetime.now(_tz.utc)

    # Pull the last 500 handoffs and reduce to the most-recent per opportunity.
    handoffs = await hsvc.list_recent(limit=500)
    last_by_opp: Dict[str, Dict[str, Any]] = {}
    for h in handoffs:
        opp_id = h.get("opportunity_id")
        if not opp_id:
            continue
        # handoffs come back sorted DESC by `at`; keep first per opp.
        if opp_id in last_by_opp:
            continue
        last_by_opp[opp_id] = h

    if not last_by_opp:
        return {"available": True, "items": []}

    # Index all opportunities so we can join without an N+1 pattern.
    all_ops = osvc.all() if hasattr(osvc, "all") else []
    by_id = {o.get("id"): o for o in all_ops if o.get("id")}

    ACTIVE_CLOSED = {"Won", "Lost", "Disqualified"}
    ESTIMATE_STATUSES = {"Estimate requested", "Estimate sent"}
    out: List[Dict[str, Any]] = []

    for opp_id, h in last_by_opp.items():
        opp = by_id.get(opp_id)
        if not opp:
            continue
        status = (opp.get("status") or "").strip()
        if status in ACTIVE_CLOSED:
            continue
        # Parse the ISO timestamp; skip if unparseable.
        raw_at = h.get("at") or ""
        try:
            last_at = datetime.fromisoformat(raw_at.replace("Z", "+00:00"))
        except Exception:
            continue
        days_since = (now - last_at).total_seconds() / 86400.0
        channel = (h.get("channel") or "").lower()

        bucket = None
        threshold = None
        if status in ESTIMATE_STATUSES and days_since >= 7:
            bucket, threshold = "estimate_check", 7
        elif channel == "email" and days_since >= 5:
            bucket, threshold = "email_nudge", 5
        elif channel == "text" and days_since >= 3:
            bucket, threshold = "text_nudge", 3
        if not bucket:
            continue

        reason = (
            f"{int(days_since)} days since your last {channel or 'touch'}"
            if bucket != "estimate_check"
            else f"{int(days_since)} days since estimate was requested"
        )

        out.append({
            "opportunity_id": opp_id,
            "opportunity": {
                "id": opp_id,
                "name": opp.get("name"),
                "status": status,
                "lane": opp.get("lane"),
                "priority_band": opp.get("priority_band"),
                "priority_score": opp.get("priority_score"),
                "estimated_value": opp.get("estimated_value"),
                "contact_phone": opp.get("contact_phone") or opp.get("phone"),
                "contact_email": opp.get("contact_email") or opp.get("email"),
                "first_message": opp.get("first_message") or opp.get("first_contact_message"),
            },
            "last_touch": {
                "channel": channel or "unknown",
                "at": raw_at,
                "days_ago": round(days_since, 1),
                "device_hint": h.get("device_hint"),
            },
            "bucket": bucket,
            "threshold_days": threshold,
            "reason": reason,
        })

    # Rank: estimate_check first, then by priority_score desc, then days desc.
    BUCKET_ORDER = {"estimate_check": 0, "text_nudge": 1, "email_nudge": 2}
    out.sort(key=lambda r: (
        BUCKET_ORDER.get(r["bucket"], 99),
        -(r["opportunity"].get("priority_score") or 0),
        -(r["last_touch"].get("days_ago") or 0),
    ))
    return {"available": True, "items": out[: max(1, min(limit, 100))]}


# ============================================================================
# Monthly KPIs — "Won this month" + active pipeline value, so Ryan can see
# how the business is trending at a glance. Uses `last_reviewed` when set,
# else `created_time`, as the "settled at" proxy. All-time Won is included
# as a stable fallback for periods with few dated records.
# ============================================================================
# ============================================================================
# Reverse Lookup — GET /api/opportunities/by-phone/{number}
# Normalizes an incoming phone (strips +1, spaces, dashes, parens) then finds
# the record whose Contact phone / Phone number best matches the same 10-digit
# tail. Ryan taps a Shortcut on his phone → app opens straight to this record.
# Read-only. Zero writes.
# ============================================================================
@api_router.get("/opportunities/by-phone/{number}")
async def find_by_phone(number: str):
    from services.opportunity_service import get_opportunity_service

    def _digits(v: Any) -> str:
        return "".join(ch for ch in str(v or "") if ch.isdigit())

    query = _digits(number)
    if len(query) < 7:
        raise HTTPException(status_code=400, detail="Phone must have at least 7 digits")
    tail = query[-10:]  # normalize to last 10 digits (drops +1 country code)

    osvc = get_opportunity_service()
    all_ops = osvc.all() if hasattr(osvc, "all") else []

    matches = []
    for o in all_ops:
        for key in ("phone", "phone_alt", "contact_phone"):
            candidate = _digits(o.get(key))
            if candidate and (candidate.endswith(tail) or tail.endswith(candidate[-10:])):
                matches.append(o)
                break

    if not matches:
        raise HTTPException(status_code=404, detail=f"No record matches {number}")

    # Prefer the highest-priority Ready-to-Contact match, then Contacted, then
    # anything else. Ryan wants the most actionable card, not the newest one.
    priority = {"Ready to Contact": 0, "Contacted": 1}
    matches.sort(key=lambda o: (
        priority.get((o.get("current_queue") or "").strip(), 9),
        -(o.get("governed_priority_score") or 0),
    ))
    return matches[0]


# ============================================================================
# Landlord Portfolio Roll-Up — GET /api/opportunities/{opp_id}/portfolio
# When viewing a landlord record, return every other landlord record that
# shares the same contact identity (email > phone tail > decision_maker name).
# Two records "belong to the same landlord" if any of these match:
#   • normalized email (case-insensitive, trimmed)
#   • last 10 digits of phone/phone_alt
#   • decision_maker string equality (case-insensitive, whitespace-trimmed)
# The current record is INCLUDED in the response with `is_current=true` so
# the UI can highlight it in the property list.
# Read-only. Zero writes.
# ============================================================================
@api_router.get("/opportunities/{opp_id}/portfolio")
async def landlord_portfolio(opp_id: str):
    from services.opportunity_service import get_opportunity_service

    def _digits_tail(v: Any) -> Optional[str]:
        d = "".join(ch for ch in str(v or "") if ch.isdigit())
        return d[-10:] if len(d) >= 7 else None

    def _norm_email(v: Any) -> Optional[str]:
        e = str(v or "").strip().lower()
        return e if "@" in e else None

    def _norm_name(v: Any) -> Optional[str]:
        n = " ".join(str(v or "").strip().lower().split())
        return n or None

    osvc = get_opportunity_service()
    current = osvc.get(opp_id) if hasattr(osvc, "get") else None
    if not current:
        raise HTTPException(status_code=404, detail=f"No opportunity {opp_id}")

    # Roll-up is landlord-only. Non-landlord records return an empty portfolio
    # so the frontend can call this endpoint unconditionally.
    if (current.get("lane") or "").lower() != "landlord":
        return {
            "portfolio": [],
            "match_key": None,
            "count": 0,
            "total_value_numeric": 0.0,
            "priced_count": 0,
            "unpriced_count": 0,
        }

    current_email = _norm_email(current.get("email") or current.get("email_alt"))
    current_phone_tail = (
        _digits_tail(current.get("phone"))
        or _digits_tail(current.get("phone_alt"))
    )
    current_name = _norm_name(current.get("decision_maker"))

    def _is_sibling(o: Dict[str, Any]) -> Optional[str]:
        """Returns the match-key type ("email", "phone", "name") or None."""
        if (o.get("lane") or "").lower() != "landlord":
            return None
        if current_email:
            for key in ("email", "email_alt"):
                if _norm_email(o.get(key)) == current_email:
                    return "email"
        if current_phone_tail:
            for key in ("phone", "phone_alt"):
                if _digits_tail(o.get(key)) == current_phone_tail:
                    return "phone"
        if current_name and _norm_name(o.get("decision_maker")) == current_name:
            return "name"
        return None

    all_ops = osvc.all() if hasattr(osvc, "all") else []
    siblings: List[Dict[str, Any]] = []
    match_key: Optional[str] = None
    for o in all_ops:
        m = _is_sibling(o)
        if not m:
            continue
        match_key = match_key or m
        siblings.append({
            "id": o.get("id"),
            "name": o.get("name"),
            "project_address": o.get("project_address"),
            "current_queue": o.get("current_queue"),
            "governed_priority_score": o.get("governed_priority_score"),
            "portfolio_size": o.get("portfolio_size"),
            "turnover_cadence": o.get("turnover_cadence"),
            "last_turnover_check": o.get("last_turnover_check"),
            "date_contacted": o.get("date_contacted"),
            "estimated_value": o.get("estimated_value"),
            "is_current": o.get("id") == opp_id,
        })

    # Highest-score first, current record floats to top for anchor context.
    siblings.sort(key=lambda r: (
        not r["is_current"],
        -(r.get("governed_priority_score") or 0),
    ))

    # Combined "Possible work value" — sums only numeric `estimated_value`
    # across the portfolio. Records with string fallbacks ("Not estimated
    # yet") are counted as unpriced. Never invents a number.
    total_numeric = 0.0
    priced_count = 0
    for r in siblings:
        raw = r.get("estimated_value")
        try:
            n = float(raw) if raw is not None else 0.0
        except (TypeError, ValueError):
            n = 0.0
        if n > 0:
            total_numeric += n
            priced_count += 1

    return {
        "portfolio": siblings,
        "match_key": match_key,
        "count": len(siblings),
        "total_value_numeric": total_numeric,
        "priced_count": priced_count,
        "unpriced_count": len(siblings) - priced_count,
    }


# ============================================================================
# Discovery — Property Manager Discovery Queue
# ----------------------------------------------------------------------------
# The Airtable base has a separate "Property Manager Discovery Queue" table
# (owned by Claude + Make). GEAUXleads is a strictly-read viewer of this
# table. Ryan uses the Discovery UI to triage "Worth a look" candidates and
# do native call/website handoff — any promote-to-Leads write happens on the
# Airtable side (Claude owns that flow).
# ============================================================================
@api_router.get("/discovery/property-managers")
async def discovery_property_managers(status: str = "worth_a_look"):
    """List property management companies from the discovery queue."""
    from services.discovery_service import list_property_managers, property_manager_status_counts
    from services.discovery_handoff_service import (
        get_discovery_handoff_service,
        FEED_PROPERTY_MANAGERS,
        is_actionable_property_manager,
    )

    items = list_property_managers(status=status)
    counts = property_manager_status_counts()

    handoff = get_discovery_handoff_service()
    fresh_ids: set = set()
    if handoff:
        actionable_ids = [i["id"] for i in items if is_actionable_property_manager(i)]
        fresh_ids = await handoff.mark_fresh(FEED_PROPERTY_MANAGERS, actionable_ids)
    for item in items:
        item["is_freshly_actionable"] = item["id"] in fresh_ids
    # Float freshly-actionable rows to the top so operator sees the newest
    # contacts at first glance.
    items.sort(key=lambda i: (not i.get("is_freshly_actionable"),))

    return {
        "items": items,
        "count": len(items),
        "status_filter": status,
        "status_counts": counts,
        "freshly_actionable_count": len(fresh_ids),
    }


@api_router.get("/discovery/real-estate-agents")
async def discovery_real_estate_agents(status: str = "all"):
    """List real-estate agents from the outreach queue."""
    from services.discovery_service import (
        list_real_estate_agents,
        real_estate_agent_status_counts,
    )
    from services.discovery_handoff_service import (
        get_discovery_handoff_service,
        FEED_REAL_ESTATE_AGENTS,
        is_actionable_agent,
    )

    items = list_real_estate_agents(status=status)
    counts = real_estate_agent_status_counts()

    handoff = get_discovery_handoff_service()
    fresh_ids: set = set()
    if handoff:
        actionable_ids = [i["id"] for i in items if is_actionable_agent(i)]
        fresh_ids = await handoff.mark_fresh(FEED_REAL_ESTATE_AGENTS, actionable_ids)
    for item in items:
        item["is_freshly_actionable"] = item["id"] in fresh_ids
    items.sort(key=lambda i: (not i.get("is_freshly_actionable"),))

    return {
        "items": items,
        "count": len(items),
        "status_filter": status,
        "status_counts": counts,
        "freshly_actionable_count": len(fresh_ids),
    }


@api_router.get("/discovery/landlords")
async def discovery_landlords(status: str = "not_contacted", ids: Optional[str] = None):
    """List STR-license landlord property owners (mail-only outreach)."""
    from services.discovery_service import list_landlords, landlord_status_counts

    id_list = [i.strip() for i in ids.split(",")] if ids else None
    items = list_landlords(status=status, ids=id_list)
    counts = landlord_status_counts()
    return {
        "items": items,
        "count": len(items),
        "status_filter": status,
        "status_counts": counts,
    }


@api_router.get("/discovery/investors")
async def discovery_investors(status: str = "all"):
    """List real estate investors / LLC entities."""
    from services.discovery_service import list_investors, investor_status_counts
    from services.discovery_handoff_service import (
        get_discovery_handoff_service,
        FEED_INVESTORS,
        is_actionable_investor,
    )

    items = list_investors(status=status)
    counts = investor_status_counts()

    handoff = get_discovery_handoff_service()
    fresh_ids: set = set()
    if handoff:
        actionable_ids = [i["id"] for i in items if is_actionable_investor(i)]
        fresh_ids = await handoff.mark_fresh(FEED_INVESTORS, actionable_ids)
    for item in items:
        item["is_freshly_actionable"] = item["id"] in fresh_ids
    items.sort(key=lambda i: (not i.get("is_freshly_actionable"),))

    return {
        "items": items,
        "count": len(items),
        "status_filter": status,
        "status_counts": counts,
        "freshly_actionable_count": len(fresh_ids),
    }


# ============================================================================
# Learning loop — reads through the opportunity list to compute reply-rate and
# win-rate patterns per governed dimension (Money Signal, Premium Fit, etc.).
# Zero writes. Zero LLM calls. Ryan sees the top ranked pattern on Home.
# ============================================================================
@api_router.get("/learning/insights")
async def learning_insights(limit: int = 3):
    from services.learning_service import compute_insights
    osvc = get_opportunity_service()
    all_ops = osvc.all() if hasattr(osvc, "all") else []
    return compute_insights(all_ops, limit=max(1, min(limit, 10)))


# ============================================================================
# Morning Brief — Ryan's 7am glance email + in-app panel. Composes the same
# dict two ways: as JSON for the frontend MorningBrief component, and as
# inline-styled HTML for the scheduled email send. The cron endpoint is
# Bearer-authed and enqueues the work in a background task so the platform
# scheduler gets its immediate 2xx ack (per skill contract).
# ============================================================================
@api_router.get("/morning-brief/preview")
async def morning_brief_preview():
    from services.morning_brief_service import compose_brief
    osvc = get_opportunity_service()
    hsvc = get_handoff_service()
    return await compose_brief(opportunity_service=osvc, handoff_service=hsvc)


async def _deliver_morning_brief(force: bool = False) -> Dict[str, Any]:
    """Compose + send the brief. Isolated so both the cron worker and the
    on-demand /send-now endpoint can call it. Never raises — logs and
    returns a status dict instead so a transient failure doesn't crash
    the cron worker or the manual test button.

    The cron fires hourly (America/Chicago); this function no-ops unless
    the current Chicago hour matches settings.brief_hour and delivery is
    enabled. `force=True` bypasses those checks — used by the manual
    Settings "Send now" button so Ryan can test-fire outside his window.
    """
    from services.morning_brief_service import compose_brief, render_brief_html
    from services.email_service import send_outreach_email, EmailSendError

    osvc = get_opportunity_service()
    hsvc = get_handoff_service()
    usvc = get_user_settings_service()

    settings = await usvc.get() if usvc else USER_SETTINGS_DEFAULTS
    if not force:
        if not settings.get("brief_enabled", True):
            return {"sent": False, "reason": "brief disabled in settings"}
        # America/Chicago local hour gate. Zoneinfo is stdlib; a bad env or
        # missing tzdata falls back to UTC hour so we never crash the cron.
        try:
            from zoneinfo import ZoneInfo
            now_local = datetime.now(ZoneInfo("America/Chicago"))
        except Exception:
            now_local = datetime.now(timezone.utc)
        want_hour = int(settings.get("brief_hour", 7))
        if now_local.hour != want_hour:
            return {"sent": False, "reason": f"hour {now_local.hour} != brief_hour {want_hour}"}

    brief = await compose_brief(opportunity_service=osvc, handoff_service=hsvc)
    recipient = (settings.get("sender_email") or "").strip()
    if not recipient:
        return {"sent": False, "reason": "no recipient in user_settings"}

    app_base = os.environ.get("PUBLIC_BACKEND_URL") or ""
    html_body = render_brief_html(brief, app_base_url=app_base.rstrip("/"))
    subject = f'Morning brief · {brief["counts"].get("total", 0)} things for today'
    try:
        result = await send_outreach_email(
            recipient_email=recipient,
            subject=subject,
            html_body=html_body,
        )
        return {"sent": True, "recipient": recipient, "email_id": result.get("id"),
                "counts": brief["counts"]}
    except EmailSendError as e:
        logger.error("Morning brief send failed: %s", e)
        return {"sent": False, "reason": str(e), "counts": brief["counts"]}


@api_router.post("/morning-brief/send-now")
async def morning_brief_send_now(authorization: Optional[str] = Header(None)):
    """Trigger a live send immediately. Bearer-gated so a stranger who
    knows the backend URL cannot fire real Resend emails against Ryan's
    inbox or burn his Resend quota. Same secret as `/api/cron/morning-brief`.
    """
    if not _bearer_matches(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")
    # Manual test-fire bypasses the hour gate so Ryan can preview delivery
    # regardless of what time it is.
    return await _deliver_morning_brief(force=True)


def _bearer_matches(auth_header: Optional[str]) -> bool:
    expected = os.environ.get("WEBHOOK_CRON_SECRET") or ""
    if not expected or not auth_header:
        return False
    if not auth_header.lower().startswith("bearer "):
        return False
    token = auth_header.split(" ", 1)[1].strip()
    return hmac.compare_digest(token, expected)


@api_router.post("/cron/morning-brief")
async def cron_morning_brief(
    background: BackgroundTasks,
    authorization: Optional[str] = Header(None),
):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    if not _bearer_matches(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")
    background.add_task(_deliver_morning_brief)
    return {"accepted": True}


@api_router.get("/kpis/monthly")
async def monthly_kpis():
    from datetime import datetime, timezone as _tz
    osvc = get_opportunity_service()
    all_ops = osvc.all() if hasattr(osvc, "all") else []

    now = datetime.now(_tz.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def _settled_at(o):
        raw = o.get("last_reviewed") or o.get("created_time") or ""
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except Exception:
            return None

    won_month = 0
    won_month_value = 0.0
    won_all_time = 0
    won_all_time_value = 0.0
    active_count = 0
    active_value = 0.0
    ESTIMATE_STATUSES = {"Estimate requested", "Estimate sent"}
    est_out_count = 0
    est_out_value = 0.0

    for o in all_ops:
        status = (o.get("status") or "").strip()
        value = float(o.get("estimated_value") or 0)
        if status == "Won":
            won_all_time += 1
            won_all_time_value += value
            settled = _settled_at(o)
            if settled and settled >= month_start:
                won_month += 1
                won_month_value += value
        elif status not in ("Lost", "Disqualified"):
            active_count += 1
            active_value += value
            if status in ESTIMATE_STATUSES:
                est_out_count += 1
                est_out_value += value

    return {
        "month_start": month_start.isoformat(),
        "won_this_month": {
            "count": won_month,
            "value": round(won_month_value, 2),
        },
        "won_all_time": {
            "count": won_all_time,
            "value": round(won_all_time_value, 2),
        },
        "active_pipeline": {
            "count": active_count,
            "value": round(active_value, 2),
        },
        "estimates_out": {
            "count": est_out_count,
            "value": round(est_out_value, 2),
        },
    }


# ============================================================================
# User settings — Ryan's per-account preferences (e.g. which sender email
# should appear in mailto: drafts). Stored in Mongo so the value survives
# preview reloads. Purely preference data; no credentials, no provider config.
# ============================================================================
class UserSettingsPatch(BaseModel):
    sender_email: Optional[str] = None
    sender_name: Optional[str] = None
    sender_phone: Optional[str] = None
    sender_mailing_address: Optional[str] = None
    email_provider: Optional[str] = None


@api_router.get("/settings/user")
async def get_user_settings():
    svc = get_user_settings_service()
    if not svc:
        return {"settings": dict(USER_SETTINGS_DEFAULTS), "persisted": False}
    return {"settings": await svc.get(), "persisted": True}


@api_router.patch("/settings/user")
async def update_user_settings(patch: UserSettingsPatch):
    svc = get_user_settings_service()
    if not svc:
        raise HTTPException(status_code=503, detail="Settings store unavailable")
    try:
        settings = await svc.update(patch.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"settings": settings, "persisted": True}


app.include_router(api_router)


# ─── Twilio Lookup (Number Intelligence) ─────────────────────────────────
# Read-only. Never sends messages. Feature-flagged: when
# TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN are absent, the routes return
# 503 cleanly and the frontend hides the enrichment card.
from services.twilio_lookup_service import (
    lookup_async as _twilio_lookup_async,
    TwilioLookupError as _TwilioLookupError,
    get_twilio_lookup_service as _get_twilio_lookup_service,
    twilio_lookup_config_error as _twilio_lookup_config_error,
)


@app.get("/api/lookup/twilio/status")
async def twilio_lookup_status():
    """Report whether Twilio Lookup is configured, without leaking creds."""
    svc = _get_twilio_lookup_service()
    return {
        "enabled": svc is not None,
        "error": _twilio_lookup_config_error() if svc is None else None,
    }


@app.get("/api/lookup/twilio/{number}")
async def twilio_lookup(number: str):
    try:
        return await _twilio_lookup_async(number)
    except _TwilioLookupError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


# ─── Auto-fill Contact — write email/phone onto a Real Estate Agent row.
# The ONLY write route GEAUXleads has into any Discovery table. Never
# touches governed fields (Outreach Gate, Contact Enrichment Status,
# etc.) — Claude/Make still own those. Cache is invalidated on success
# so the next agent-list fetch reflects the new contact immediately.
class AgentEnrichRequest(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None


@app.post("/api/discovery/real-estate-agents/{record_id}/enrich")
async def enrich_agent_contact(record_id: str, req: AgentEnrichRequest):
    from services.discovery_service import enrich_real_estate_agent
    try:
        return await asyncio.to_thread(
            enrich_real_estate_agent,
            record_id,
            req.email,
            req.phone,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        msg = str(e)
        # Missing schema.bases:write PAT scope — surface with exact next step.
        if "schema.bases:write" in msg or "INVALID_PERMISSIONS" in msg:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Airtable rejected the auto-column-create because your "
                    "Personal Access Token is missing the "
                    "'schema.bases:write' scope. Update the PAT at "
                    "https://airtable.com/create/tokens and paste the new "
                    "value into AIRTABLE_API_KEY. This is a one-time setup."
                ),
            )
        # Any other Airtable-side failure.
        raise HTTPException(status_code=502, detail=msg[:280])


# ─── Local archive + CSV export + telemetry ─────────────────────────────
from services import local_state_service as _local_state
from services import csv_export_service as _csv_export
from fastapi.responses import Response


class LocalArchiveRequest(BaseModel):
    record_ids: List[str]


@app.get("/api/local-state/{feed}/archived")
async def get_archived(feed: str):
    try:
        ids = await _local_state.list_archived(feed)
        return {"feed": feed, "archived_ids": ids}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/local-state/{feed}/archive")
async def archive_local(feed: str, req: LocalArchiveRequest):
    try:
        n = await _local_state.archive_many(feed, req.record_ids)
        return {"feed": feed, "archived": n}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/local-state/{feed}/unarchive")
async def unarchive_local(feed: str, req: LocalArchiveRequest):
    try:
        n = await _local_state.unarchive_many(feed, req.record_ids)
        return {"feed": feed, "unarchived": n}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class TelemetryEvent(BaseModel):
    event: str
    payload: Optional[Dict[str, Any]] = None


@app.post("/api/telemetry/event")
async def telemetry_event(evt: TelemetryEvent):
    if os.environ.get("BLOODHOUND_TELEMETRY_ENABLED", "").lower() != "true":
        return {"stored": False}
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]["bloodhound_events"]
        await c.insert_one({
            "event": evt.event[:80],
            "payload": evt.payload or {},
            "at": datetime.now(timezone.utc).isoformat(),
        })
        return {"stored": True}
    except Exception:
        return {"stored": False}


def _csv_response(feed: str, rows):
    body = _csv_export.build_csv(feed, rows)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{_csv_export.filename_for(feed)}"',
            "Cache-Control": "no-store",
        },
    )


@app.get("/api/exports/opportunities.csv")
async def export_opportunities_csv(
    source: Optional[str] = None,
    status: Optional[str] = None,
    priority_band: Optional[str] = None,
    daily_mission: Optional[str] = None,
    project_type: Optional[str] = None,
    min_score: Optional[float] = None,
    q: Optional[str] = None,
    lane: Optional[str] = None,
    sort: Optional[str] = "lead_score",
    view: Optional[str] = None,
):
    """Export the CURRENTLY-FILTERED opportunities view. Accepts the same
    query params as GET /api/opportunities so the CSV always matches what
    the operator sees on-screen."""
    svc = get_opportunity_service()
    rows = svc.list(
        source=source, status=status, priority_band=priority_band,
        daily_mission=daily_mission, project_type=project_type,
        min_score=min_score, q=q, lane=lane, sort=sort, view=view,
    ) if svc else []
    return _csv_response("leads", rows)


@app.get("/api/exports/discovery/{feed}.csv")
async def export_discovery_csv(feed: str):
    from services.discovery_service import (
        list_property_managers, list_real_estate_agents,
        list_landlords, list_investors,
    )
    mapping = {
        "property-managers": ("property_managers", list_property_managers),
        "real-estate-agents": ("re_agents", list_real_estate_agents),
        "landlords": ("landlords", list_landlords),
        "investors": ("investors", list_investors),
    }
    if feed not in mapping:
        raise HTTPException(status_code=404, detail="unknown feed")
    key, fn = mapping[feed]
    result = fn(status="all") if fn.__code__.co_argcount else fn()
    items = result.get("items", []) if isinstance(result, dict) else (result or [])
    return _csv_response(key, items)


# ─── Portfolio Check proxy ─────────────────────────────────────────────
# Fire-and-forget POST to the Make.com webhook Claude/Make owns. Real web
# search runs behind it (~15-30 sec); Make writes results into 12
# `Portfolio *` fields on the same Airtable record. GEAUXleads polls
# opportunity data after the fact — no direct reply is expected here.
# GEAUXleads never crawls or scores; this endpoint is a thin proxy so the
# webhook URL doesn't get exposed in the browser and CORS is handled
# server-side.
# ============================================================================
import re as _re_portfolio
import httpx as _httpx_portfolio

_RECORD_ID_RE = _re_portfolio.compile(r"^rec[A-Za-z0-9]{14,}$")


@app.post("/api/leads/{record_id}/portfolio-check", status_code=202)
async def portfolio_check(record_id: str):
    """Trigger Claude/Make's Portfolio Check webhook for a single lead.
    Returns 202 immediately — results land in Airtable after ~15-30 sec
    and the frontend re-fetches the opportunity to display them."""
    if not _RECORD_ID_RE.match(record_id):
        raise HTTPException(status_code=400, detail="invalid record_id format")
    webhook = os.environ.get("MAKE_PORTFOLIO_CHECK_WEBHOOK", "").strip()
    if not webhook:
        raise HTTPException(status_code=503, detail="portfolio check webhook not configured")
    try:
        async with _httpx_portfolio.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook, json={"record_id": record_id})
            if resp.status_code >= 400:
                logger.warning("Portfolio webhook returned %s: %s", resp.status_code, resp.text[:200])
                raise HTTPException(status_code=502, detail=f"webhook rejected: {resp.status_code}")
    except _httpx_portfolio.RequestError as e:
        logger.error("Portfolio webhook request error: %s", e)
        raise HTTPException(status_code=502, detail="could not reach portfolio webhook")
    return {"accepted": True, "record_id": record_id,
            "hint": "results land in ~15-30 seconds; refetch the opportunity"}


# ─── Draft safety audit ────────────────────────────────────────────────
# Scans every opportunity for message-shaped fields that would fail the
# frontend `looksLikeAIPrompt` guard — meaning: if Ryan had tapped
# Email Now on that record, an unrendered AI prompt or template stub
# would have flowed into the mailto body. Read-only; touches nothing.
# ============================================================================
@app.get("/api/audit/draft-safety")
async def audit_draft_safety():
    from services.draft_safety import looks_like_ai_prompt
    svc = get_opportunity_service()
    all_ops = svc.all() if (svc and hasattr(svc, "all")) else []
    # Every Airtable field the composer trusts as part of a mailto: draft.
    # Body sources — piped straight into the email body:
    BODY_FIELDS = ("first_message", "first_contact_message", "current_recommendation")
    # Subject sources — piped into the subject line:
    SUBJECT_FIELDS = ("first_message_subject",)
    # Salutation sources — piped into "Hi X," at the top of the body. A bad
    # value here becomes literally "Hi You are a Claude assistant,".
    NAME_FIELDS = ("decision_maker", "contact_name")
    ALL_FIELDS = BODY_FIELDS + SUBJECT_FIELDS + NAME_FIELDS
    offenders = []
    reason_counts: Dict[str, int] = {}
    field_counts: Dict[str, int] = {}
    for o in all_ops:
        for field in ALL_FIELDS:
            val = o.get(field)
            if not val:
                continue
            trip, reason = looks_like_ai_prompt(val)
            if not trip:
                continue
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            field_counts[field] = field_counts.get(field, 0) + 1
            offenders.append({
                "id": o.get("id"),
                "name": o.get("name"),
                "field": field,
                "reason": reason,
                "sample": (str(val).strip()[:220]),
                "current_queue": o.get("current_queue"),
                "outreach_status": o.get("outreach_status"),
                "outreach_sent": bool(o.get("flag_outreach_sent") or o.get("outreach_sent")),
                "message_sent_date": o.get("message_sent_date"),
            })
    sent_offenders = [x for x in offenders if x["outreach_sent"]]
    return {
        "scanned": len(all_ops),
        "fields_checked": list(ALL_FIELDS),
        "offender_count": len(offenders),
        "reason_counts": reason_counts,
        "field_counts": field_counts,
        "sent_with_bad_body_count": len(sent_offenders),
        "sent_with_bad_body": sent_offenders,
        "offenders": offenders,
    }



# ─── Perplexity research routes ─────────────────────────────────────────
# Feature-flagged: when PERPLEXITY_API_KEY is not set, /api/research
# returns 503 cleanly and the frontend hides the research buttons.
from services.perplexity_service import (
    research_async as _pplx_research_async,
    PerplexityError as _PerplexityError,
    get_perplexity_service as _get_pplx_service,
    perplexity_config_error as _pplx_config_error,
)
from services import research_cache_service as _research_cache


class ResearchRequest(BaseModel):
    research_type: str  # decision_maker | permit_explainer | landlord_background
    record_id: str
    query: str
    force_refresh: Optional[bool] = False


@app.get("/api/research/status")
async def research_status():
    """Report whether Perplexity is configured, without leaking the key."""
    svc = _get_pplx_service()
    return {
        "enabled": svc is not None,
        "error": _pplx_config_error() if svc is None else None,
    }


@app.post("/api/research")
async def create_research(req: ResearchRequest):
    if req.research_type not in (
        "decision_maker",
        "permit_explainer",
        "landlord_background",
        "re_agent_background",
    ):
        raise HTTPException(status_code=400, detail="unknown research_type")

    # Serve from Mongo cache unless the caller asked for a fresh call.
    if not req.force_refresh:
        try:
            cached = await _research_cache.get_cached(req.research_type, req.record_id)
            if cached:
                return cached
        except Exception:  # noqa: BLE001
            logger.exception("research cache read failed — falling through to Perplexity")

    try:
        result = await _pplx_research_async(req.research_type, req.query)
    except _PerplexityError as e:
        headers = {"Retry-After": e.retry_after} if e.retry_after else None
        raise HTTPException(status_code=e.status_code, detail=str(e), headers=headers)

    try:
        await _research_cache.set_cached(req.research_type, req.record_id, result)
    except Exception:  # noqa: BLE001
        logger.exception("research cache write failed — returning result anyway")

    return result


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
