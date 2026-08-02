from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
from pathlib import Path
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone

from services.audit import get_audit_log
from services.opportunity_service import get_opportunity_service, reset_opportunity_service
from services.leads_service import OutreachBlocked, get_leads_service, reset_leads_service


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

app = FastAPI(title="Bloodhound Intelligence API")
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
    )


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


@api_router.get("/opportunities/duplicates")
async def opportunity_duplicates():
    """Duplicate groups and which record was elected canonical.

    Declared before /opportunities/{opp_id} so the literal path wins the match.
    """
    svc = get_opportunity_service()
    if not hasattr(svc, "duplicates_report"):
        return {"backend": svc.backend_name, "duplicate_groups": 0, "groups": []}
    return svc.duplicates_report()


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
    payload = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not payload:
        raise HTTPException(status_code=400, detail="No editable fields provided")
    if hasattr(svc, "update_fields"):
        updated = svc.update_fields(opp_id, payload)
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
    action: str  # approve | revert_approval | hold | skip | do_not_contact
    confirm: Optional[bool] = False
    # Supplied by the client so a double-click or a retried request approves
    # once. Derived server-side (action + lead + UTC day) when omitted.
    idempotency_key: Optional[str] = None
    actor: Optional[str] = None
    reason: Optional[str] = None
    # Warning codes the operator explicitly saw and accepted in the confirm
    # dialog. Recorded on the audit event; warnings never gate the write.
    acknowledged_warnings: Optional[List[str]] = None


class LeadMessageUpdate(BaseModel):
    message: str
    actor: Optional[str] = None


def _require_leads_service():
    svc = get_leads_service()
    if not svc:
        raise HTTPException(status_code=503, detail="Leads service not available")
    return svc


def _blocked_response(exc: OutreachBlocked) -> JSONResponse:
    """409 rather than 400: the request was well-formed, the record's current
    state is what forbids it. Carries the structured verdict so the UI can list
    every blocker instead of showing one opaque error."""
    return JSONResponse(
        status_code=409,
        content={
            "detail": "Lead is not eligible for outreach.",
            "error": "outreach_blocked",
            "eligibility": exc.result.to_dict(),
        },
    )


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


@api_router.get("/leads/duplicates")
async def leads_duplicates():
    svc = _require_leads_service()
    return svc.duplicates_report()


@api_router.get("/leads/{lead_id}/eligibility")
async def leads_eligibility(lead_id: str):
    """Read-only policy verdict. The UI uses this to disable and explain the
    approve control; the server re-evaluates on write regardless."""
    svc = _require_leads_service()
    result = svc.eligibility_for_id(lead_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")
    return result.to_dict()


@api_router.get("/leads/{lead_id}/readiness")
async def leads_readiness(lead_id: str):
    """Missing fields and risk derived from live field values. Any AI-generated
    prose is returned under `advisory_*` keys and never drives eligibility."""
    svc = _require_leads_service()
    report = svc.readiness(lead_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")
    return report


@api_router.post("/leads/{lead_id}/action")
async def leads_action(lead_id: str, body: LeadAction):
    svc = _require_leads_service()
    if svc.get(lead_id) is None:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")
    action = (body.action or "").lower()
    if action == "approve":
        if not body.confirm:
            raise HTTPException(
                status_code=400,
                detail="Confirmation required for Approve — the operator must "
                       "acknowledge the recipient and any warnings.",
            )
        try:
            return svc.approve(lead_id,
                               idempotency_key=body.idempotency_key,
                               actor=body.actor,
                               acknowledged_warnings=body.acknowledged_warnings)
        except OutreachBlocked as exc:
            return _blocked_response(exc)
    if action == "revert_approval":
        return svc.revert_approval(lead_id, actor=body.actor, reason=body.reason)
    if action == "hold":
        return svc.hold(lead_id, actor=body.actor)
    if action == "skip":
        return svc.skip(lead_id, actor=body.actor)
    if action == "do_not_contact":
        if not body.confirm:
            raise HTTPException(status_code=400,
                                detail="Confirmation required for Do Not Contact")
        return svc.do_not_contact(lead_id, actor=body.actor)
    raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")


@api_router.patch("/leads/{lead_id}/message")
async def leads_update_message(lead_id: str, body: LeadMessageUpdate):
    svc = _require_leads_service()
    updated = svc.update_message(lead_id, body.message, actor=body.actor)
    if not updated:
        raise HTTPException(status_code=404, detail="Message update failed")
    return updated


# ---------- Audit & ingestion diagnostics ----------

@api_router.get("/audit/events")
async def audit_events(limit: int = 50, entity_id: Optional[str] = None,
                       action: Optional[str] = None):
    """Recent decisions from the in-process sink.

    Empty after a restart — the durable record is the structured `audit ...`
    log line. See docs/INTEGRATIONS.md for swapping in a persistent sink.
    """
    events = get_audit_log().recent(limit=limit, entity_id=entity_id, action=action)
    return {"events": events, "count": len(events), "durable": False}


@api_router.get("/diagnostics/ingestion")
async def ingestion_diagnostics_report():
    svc = get_opportunity_service()
    if not hasattr(svc, "ingestion_report"):
        return {
            "backend": svc.backend_name,
            "note": "Ingestion diagnostics require the live Airtable backend.",
        }
    return svc.ingestion_report()


@api_router.post("/admin/reload")
async def reload_service():
    reset_opportunity_service()
    svc = get_opportunity_service()
    return {"ok": True, "backend": svc.backend_name}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
