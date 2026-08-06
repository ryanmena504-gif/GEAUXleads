from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import json
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone

from services.opportunity_service import get_opportunity_service, reset_opportunity_service
from services.leads_service import get_leads_service, reset_leads_service
from services.airtable_service import AirtableWriteError
from services.email_service import send_outreach_email, EmailSendError
from services.slack_service import (
    get_slack_alerter,
    is_configured as slack_is_configured,
)
from services.playbook_service import get_playbook_service
from services.draft_service import get_draft_service, REVIEW_STATUSES
from services.handoff_service import get_handoff_service
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


app = FastAPI(title="Bloodhound Intelligence API", lifespan=lifespan)
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


@api_router.get("/")
async def root():
    return {"service": "Bloodhound Intelligence API", "status": "online"}


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


@api_router.get("/config")
async def config():
    svc = get_opportunity_service()
    return {
        "airtable_configured": bool(
            os.environ.get("AIRTABLE_API_KEY")
            and os.environ.get("AIRTABLE_BASE_ID")
            and os.environ.get("AIRTABLE_OPPORTUNITIES_TABLE")
        ),
        "airtable_enabled": os.environ.get("AIRTABLE_ENABLED", "").lower() == "true",
        "backend": svc.backend_name,
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
    action: str  # approve | hold | skip | do_not_contact
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
    svc = get_leads_service()
    if not svc:
        raise HTTPException(status_code=503, detail="Leads service not available")
    if svc.get(lead_id) is None:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")
    action = (body.action or "").lower()
    if action == "approve":
        # Two-phase: mark session-approved, then actually send the email.
        session = svc.approve(lead_id)
        gate = svc.can_send(lead_id)
        if not gate["ok"]:
            raise HTTPException(status_code=422, detail=gate["reason"])
        lead = gate["lead"]
        recipient = gate["recipient"]
        email = svc.compose_email(lead)
        try:
            provider = await send_outreach_email(
                recipient_email=recipient,
                subject=email["subject"],
                html_body=email["html"],
                text_body=email["text"],
                reply_to=os.environ.get("EMAIL_REPLY_TO"),
            )
        except EmailSendError as e:
            # DO NOT mark sent — leave the lead in the approval queue.
            raise HTTPException(status_code=e.status_code,
                                detail=f"Email send failed: {e}")
        persisted = svc.mark_sent(
            lead_id,
            sent_at_iso=session["approved_at"],
            channel="Email",
            first_message_written=email["text"] if email["used_fallback"] else None,
        )
        return {
            "lead_id": lead_id,
            "state": "sent",
            "approved_at": session["approved_at"],
            "channel": "Email",
            "recipient": recipient,
            "used_fallback_template": email["used_fallback"],
            "provider_id": provider.get("id"),
            "persisted": persisted,
            "note": "Email sent to lead.",
        }
    if action == "hold":
        return svc.hold(lead_id)
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


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
