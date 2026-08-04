"""
Leads-table service for the Next Best Action panel.

Independent of the Opportunities service. Reads the `Leads` table on the same
Airtable base, uses a schema-driven field map (never renames Airtable fields),
and enforces a strict write allowlist for approve / hold / do-not-contact /
message-edit actions.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pyairtable import Api

log = logging.getLogger("bloodhound.leads")


# Exact Airtable field name (case-sensitive) -> internal snake_case key.
LEADS_FIELD_MAP: Dict[str, str] = {
    "Leads Name": "name",
    "Business name": "business_name",
    "Opportunity type": "opportunity_type",
    "Source": "source",
    "Source category": "source_category",
    "Source URL": "source_url",
    "Lead score": "lead_score",
    "Priority": "priority",
    "Status": "status",
    "Ai summary": "ai_summary",
    "Why lead matters": "why_lead_matters",
    "Next action": "next_action",
    "First message": "first_message",
    "Approval status": "approval_status",
    "Outreach status": "outreach_status",
    "Enrichment status": "enrichment_status",
    "Hunt status": "hunt_status",
    "Estimated job value": "estimated_job_value",
    "contact confidence": "contact_confidence",
    "Contact name": "contact_name",
    "Contact phone": "contact_phone",
    "Contact email": "contact_email",
    "Contact company": "contact_company",
    "Phone number": "phone_number",
    "Email": "email",
    "Address": "address",
    "City": "city",
    "Date discovered": "date_discovered",
    "Verified opportunity": "verified_opportunity",
    "Contact found": "contact_found",
    "Qualified opportunity": "qualified_opportunity",
    "Outreach sent": "outreach_sent",
    "Job won": "job_won",
    "Message sent date": "message_sent_date",
    "Best contact method": "best_contact_method",
    "Outreach channel": "outreach_channel",
    "SCORE band": "score_band",
    "Recommended offer": "recommended_offer",
    "Outreach angle": "outreach_angle",
}

# Only these Airtable fields may ever be written by this service.
EDITABLE_FIELDS = {
    "Approval status",
    "Outreach status",
    "Status",
    "First message",
    "Outreach sent",       # checkbox flipped after a successful send
    "Message sent date",   # datetime
    "Outreach channel",    # single-select (Email / SMS / …)
    "Hunt status",
}

# Do-not-send guardrails (case-insensitive substring matches).
_DO_NOT_SEND_STATUS = ("do not contact", "dnc")
_DO_NOT_SEND_HUNT   = ("rejected", "closed", "disqualified")

# Fixed fallback template used when a lead has no `First message` yet.
_FALLBACK_SUBJECT = "Following up on your {opportunity_type} permit at {project_address}"
_FALLBACK_TEXT = (
    "Hi {first_name},\n\n"
    "I saw the recent {opportunity_type} permit at {project_address} and wanted "
    "to reach out — I run a small local team in New Orleans and we specialize "
    "in exactly this kind of work. Happy to swing by, take a look, and give you "
    "a straight quote if you're still evaluating options.\n\n"
    "Reply anytime — no pressure.\n\n"
    "— Ryan"
)

# Case-insensitive substring match — any lead whose Status / Outreach status /
# Approval status contains one of these is excluded from the action queue.
EXCLUDE_TOKENS = ("duplicate", "do not contact", "sent", "closed", "complete")

PRIORITY_RANK = {"urgent": 4, "high": 3, "medium": 2, "normal": 2, "low": 1}


_LANE_LABELS = {
    "market_capture": "Market Capture",
    "partner": "Partner Pipeline",
    "non_permit": "Non-Permit Signals",
}
_PARTNER_TYPE_TOKENS = ("contractor", "remodel", "designer", "architect",
                        "supplier", "vendor", "referral", "partner")
_PARTNER_SOURCE_TOKENS = ("partner", "referral", "network", "trade")


def _derive_lane_from_lead(dto: Dict[str, Any]) -> str:
    otype = (dto.get("opportunity_type") or "")
    otype_l = otype.lower() if isinstance(otype, str) else ""
    if any(tok in otype_l for tok in _PARTNER_TYPE_TOKENS):
        return "partner"
    src_cat = (dto.get("source_category") or "")
    src_cat_l = src_cat.lower() if isinstance(src_cat, str) else ""
    src = (dto.get("source") or "")
    src_l = src.lower() if isinstance(src, str) else ""
    if any(tok in src_cat_l for tok in _PARTNER_SOURCE_TOKENS) \
            or any(tok in src_l for tok in _PARTNER_SOURCE_TOKENS):
        return "partner"
    if src_l and "permit" not in src_l and "permit" not in src_cat_l:
        return "non_permit"
    return "market_capture"


class LeadsAirtableService:
    def __init__(self, api_key: str, base_id: str, table_name: str = "Leads",
                 cache_ttl: float = 45.0):
        self._api = Api(api_key)
        self._base_id = base_id
        self._table_name = table_name
        self._table = self._api.table(base_id, table_name)
        self._table_id: Optional[str] = None
        self._cache_ttl = cache_ttl
        self._lock = threading.Lock()
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._last_refresh: float = 0.0
        self._field_map: Dict[str, str] = {}
        # Per-process session state — reset on backend restart.
        self._skipped: set = set()
        self._held: set = set()
        self._approvals: Dict[str, str] = {}
        self._load_schema()

    # ---------- schema ----------
    def _load_schema(self) -> None:
        base = self._api.base(self._base_id)
        schema = base.schema()
        table = next(
            (t for t in schema.tables if t.name == self._table_name),
            None,
        )
        if table is None:
            raise RuntimeError(
                f"Leads table '{self._table_name}' not found in base '{self._base_id}'"
            )
        self._table_id = table.id
        available = {f.name for f in table.fields}
        self._field_map = {
            at: sn for at, sn in LEADS_FIELD_MAP.items() if at in available
        }
        missing = sorted(set(LEADS_FIELD_MAP) - set(self._field_map))
        log.info("Leads: schema loaded — %d fields mapped, %d missing (%s)",
                 len(self._field_map), len(missing), ", ".join(missing) or "none")

    # ---------- cache ----------
    def _refresh_cache(self, force: bool = False) -> None:
        now = time.time()
        if not force and (now - self._last_refresh) < self._cache_ttl and self._cache:
            return
        try:
            records = self._table.all()
        except Exception:
            log.exception("Leads: refresh failed")
            return
        new_cache: Dict[str, Dict[str, Any]] = {}
        for r in records:
            dto = self._record_to_dto(r)
            if dto.get("id"):
                new_cache[dto["id"]] = dto
        with self._lock:
            self._cache = new_cache
            self._last_refresh = now

    def _record_to_dto(self, record: Dict[str, Any]) -> Dict[str, Any]:
        fields = record.get("fields", {}) or {}
        dto: Dict[str, Any] = {
            "id": record.get("id"),
            "created_time": record.get("createdTime"),
        }
        for at_name, snake in self._field_map.items():
            dto[snake] = fields.get(at_name)
        # Compose a stable Airtable URL for "Open Full Lead"
        if self._table_id and dto["id"]:
            dto["_airtable_url"] = f"https://airtable.com/{self._base_id}/{self._table_id}/{dto['id']}"
        # Lane classification — mirror airtable_service._derive_lane so the NBA
        # panel can label the lead consistently with the rest of the dashboard.
        dto["lane"] = _derive_lane_from_lead(dto)
        dto["lane_label"] = _LANE_LABELS.get(dto["lane"], dto["lane"])
        return dto

    def all(self) -> List[Dict[str, Any]]:
        self._refresh_cache()
        with self._lock:
            return [deepcopy(v) for v in self._cache.values()]

    def get(self, lead_id: str) -> Optional[Dict[str, Any]]:
        self._refresh_cache()
        with self._lock:
            cached = self._cache.get(lead_id)
            return deepcopy(cached) if cached else None

    # ---------- selection logic ----------
    def _is_excluded(self, lead: Dict[str, Any]) -> bool:
        if lead["id"] in self._held:
            return True
        if lead.get("job_won") is True:
            return True
        # A lead is not actionable without a name AND a recommended next action.
        # Empty/skeleton rows in Airtable must never surface as the NBA.
        name = (lead.get("name") or "").strip() if isinstance(lead.get("name"), str) else ""
        next_action = (lead.get("next_action") or "").strip() if isinstance(lead.get("next_action"), str) else ""
        if not name or not next_action:
            return True
        for key in ("status", "outreach_status", "approval_status"):
            v = (lead.get(key) or "")
            v = v if isinstance(v, str) else str(v)
            low = v.lower()
            if any(tok in low for tok in EXCLUDE_TOKENS):
                return True
        return False

    def _completeness(self, lead: Dict[str, Any]) -> int:
        """Higher is better. Rewards leads with rich, actionable data."""
        score = 0
        for k in ("name", "next_action"):
            if lead.get(k):
                score += 2
        for k in ("first_message", "why_lead_matters", "ai_summary",
                  "opportunity_type", "source", "priority", "lead_score"):
            if lead.get(k):
                score += 1
        if self._has_usable_contact(lead):
            score += 3
        return score

    def _has_usable_contact(self, lead: Dict[str, Any]) -> bool:
        return bool(
            lead.get("contact_phone") or lead.get("contact_email")
            or lead.get("phone_number") or lead.get("email")
            or lead.get("verified_opportunity") or lead.get("contact_found")
        )

    def _ai_complete(self, lead: Dict[str, Any]) -> bool:
        s = (lead.get("enrichment_status") or "")
        s = s.lower() if isinstance(s, str) else ""
        return ("complete" in s) or ("done" in s) or ("ready" in s)

    def _priority_rank(self, priority: Any) -> int:
        if not priority:
            return 0
        s = str(priority).lower()
        for k, v in PRIORITY_RANK.items():
            if k in s:
                return v
        return 0

    def _explain(self, lead: Dict[str, Any]) -> str:
        parts: List[str] = []
        if self._ai_complete(lead):
            parts.append("AI enrichment complete")
        if self._has_usable_contact(lead):
            parts.append("verified contact")
        if lead.get("priority"):
            parts.append(f"priority {lead['priority']}")
        if lead.get("lead_score"):
            parts.append(f"score {lead['lead_score']}")
        if lead.get("opportunity_type"):
            parts.append(str(lead["opportunity_type"]).lower())
        if lead.get("source"):
            parts.append(f"from {lead['source']}")
        return " · ".join(parts) if parts else "top of actionable queue"

    def pick_next_best_action(self) -> Optional[Dict[str, Any]]:
        candidates = [
            l for l in self.all()
            if not self._is_excluded(l) and l["id"] not in self._skipped
        ]
        if not candidates:
            return None
        # Canonical: `Lead score` DESC first — the single primary priority.
        # Ties: freshness DESC, then id ASC. Unscored records land LAST.
        def _score(l):
            s = l.get("lead_score")
            return s if isinstance(s, (int, float)) else None
        def _date(l):
            return l.get("date_discovered") or l.get("created_time") or ""
        scored   = [l for l in candidates if _score(l) is not None]
        unscored = [l for l in candidates if _score(l) is None]
        scored.sort(key=lambda l: l["id"])
        scored.sort(key=lambda l: _date(l), reverse=True)
        scored.sort(key=lambda l: -_score(l))
        unscored.sort(key=lambda l: l["id"])
        ordered = scored + unscored
        pick = ordered[0]
        pick["_selection_reason"] = self._explain(pick)
        if pick["id"] in self._approvals:
            pick["_approved_at"] = self._approvals[pick["id"]]
        return pick

    def queue_stats(self) -> Dict[str, int]:
        total = len(self.all())
        eligible = sum(
            1 for l in self.all()
            if not self._is_excluded(l) and l["id"] not in self._skipped
        )
        return {
            "total": total,
            "eligible": eligible,
            "skipped_this_session": len(self._skipped),
            "on_hold": len(self._held),
            "approved_this_session": len(self._approvals),
        }

    # ---------- writes (strict allowlist) ----------
    def _safe_update(self, lead_id: str, at_field: str, value: Any) -> bool:
        if at_field not in EDITABLE_FIELDS or at_field not in self._field_map:
            return False
        try:
            self._table.update(lead_id, {at_field: value})
            return True
        except Exception:
            log.exception("Leads: update %s=%s failed on %s", at_field, value, lead_id)
            return False

    def approve(self, lead_id: str) -> Dict[str, Any]:
        ts = datetime.now(timezone.utc).isoformat()
        self._approvals[lead_id] = ts
        wrote_approval = self._safe_update(lead_id, "Approval status", "Approved")
        wrote_outreach = self._safe_update(lead_id, "Outreach status", "Approved")
        self._refresh_cache(force=True)
        return {
            "lead_id": lead_id,
            "state": "approved",
            "approved_at": ts,
            "persisted": {"Approval status": wrote_approval, "Outreach status": wrote_outreach},
            "note": "Approved — awaiting messaging connection.",
        }

    def hold(self, lead_id: str) -> Dict[str, Any]:
        self._held.add(lead_id)
        wrote = self._safe_update(lead_id, "Outreach status", "Hold")
        self._refresh_cache(force=True)
        return {"lead_id": lead_id, "state": "hold", "persisted": wrote}

    def skip(self, lead_id: str) -> Dict[str, Any]:
        self._skipped.add(lead_id)
        return {"lead_id": lead_id, "state": "skipped"}

    def do_not_contact(self, lead_id: str) -> Dict[str, Any]:
        # Prefer Status; if unwritable/absent, try Outreach status; then Approval status.
        for field in ("Status", "Outreach status", "Approval status"):
            if self._safe_update(lead_id, field, "Do Not Contact"):
                self._refresh_cache(force=True)
                return {"lead_id": lead_id, "state": "do_not_contact", "persisted_to": field}
        # Fallback: session-only exclude
        self._held.add(lead_id)
        return {"lead_id": lead_id, "state": "do_not_contact", "persisted_to": None,
                "note": "Session-only (no writable Status field found)"}

    def update_message(self, lead_id: str, message: str) -> Optional[Dict[str, Any]]:
        if not self._safe_update(lead_id, "First message", message):
            return None
        self._refresh_cache(force=True)
        return self.get(lead_id)

    # ---------- outreach send ----------
    def _first_name(self, lead: Dict[str, Any]) -> str:
        raw = lead.get("contact_name") or lead.get("name") or "there"
        raw = str(raw).strip()
        return raw.split()[0] if raw else "there"

    def _recipient(self, lead: Dict[str, Any]) -> Optional[str]:
        for k in ("contact_email", "email"):
            v = lead.get(k)
            if isinstance(v, str) and "@" in v:
                return v.strip()
        return None

    def can_send(self, lead_id: str) -> Dict[str, Any]:
        """Guardrails. Returns {ok:bool, reason:str, lead:...}."""
        lead = self.get(lead_id)
        if not lead:
            return {"ok": False, "reason": "Lead not found", "lead": None}
        recipient = self._recipient(lead)
        if not recipient:
            return {"ok": False, "reason": "Lead has no contact email on file",
                    "lead": lead}
        status = (lead.get("status") or "")
        status_l = status.lower() if isinstance(status, str) else ""
        if any(tok in status_l for tok in _DO_NOT_SEND_STATUS):
            return {"ok": False, "reason": f"Blocked by Status={status!r}",
                    "lead": lead}
        hunt = (lead.get("hunt_status") or "")
        hunt_l = hunt.lower() if isinstance(hunt, str) else ""
        if any(tok in hunt_l for tok in _DO_NOT_SEND_HUNT):
            return {"ok": False, "reason": f"Blocked by Hunt status={hunt!r}",
                    "lead": lead}
        # `Rejection reason` — snake key not mapped here; check any *rejection*
        # field surfaced by the schema, plus outreach_status containing 'reject'.
        outreach_l = (lead.get("outreach_status") or "").lower() if isinstance(lead.get("outreach_status"), str) else ""
        if "reject" in outreach_l:
            return {"ok": False, "reason": "Blocked by Outreach status rejection",
                    "lead": lead}
        # Approval status must be Approved (session-level or already-persisted).
        appr = (lead.get("approval_status") or "").lower() if isinstance(lead.get("approval_status"), str) else ""
        session_approved = lead_id in self._approvals
        if not session_approved and "approved" not in appr:
            return {"ok": False,
                    "reason": "Lead is not approved — click Approve first",
                    "lead": lead}
        return {"ok": True, "reason": "ready", "lead": lead, "recipient": recipient}

    def compose_email(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Return {subject, html, text, used_fallback}."""
        first_message = lead.get("first_message")
        if isinstance(first_message, str) and first_message.strip():
            text = first_message.strip()
            subject = (
                f"Following up on your {lead.get('opportunity_type') or 'project'}"
                + (f" at {lead.get('address')}" if lead.get("address") else "")
            )
            used_fallback = False
        else:
            ctx = {
                "first_name": self._first_name(lead),
                "opportunity_type": (lead.get("opportunity_type") or "recent").strip(),
                "project_address": (lead.get("address") or "your property").strip(),
            }
            subject = _FALLBACK_SUBJECT.format(**ctx)
            text = _FALLBACK_TEXT.format(**ctx)
            used_fallback = True
        # Minimal HTML — inline styles only, no external assets.
        html = (
            '<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;'
            'font-size:15px;line-height:1.55;color:#222;max-width:560px;">'
            + "".join(f"<p style=\"margin:0 0 12px 0;\">{para}</p>"
                      for para in text.split("\n\n") if para.strip())
            + "</div>"
        )
        return {"subject": subject, "html": html, "text": text,
                "used_fallback": used_fallback}

    def mark_sent(self, lead_id: str, *, sent_at_iso: str,
                  channel: str = "Email",
                  first_message_written: Optional[str] = None) -> Dict[str, Any]:
        """After a successful send, persist the send-side fields on Airtable."""
        persisted: Dict[str, bool] = {}
        # Order matters: mark sent BEFORE approval so it hides from queue immediately.
        persisted["Outreach sent"] = self._safe_update(lead_id, "Outreach sent", True)
        persisted["Message sent date"] = self._safe_update(lead_id, "Message sent date", sent_at_iso)
        persisted["Outreach channel"] = self._safe_update(lead_id, "Outreach channel", channel)
        persisted["Approval status"] = self._safe_update(lead_id, "Approval status", "Approved")
        persisted["Outreach status"] = self._safe_update(lead_id, "Outreach status", "Sent")
        if first_message_written:
            persisted["First message"] = self._safe_update(lead_id, "First message",
                                                           first_message_written)
        self._refresh_cache(force=True)
        return persisted


_singleton: Optional[LeadsAirtableService] = None


def get_leads_service() -> Optional[LeadsAirtableService]:
    global _singleton
    if _singleton is not None:
        return _singleton
    if os.environ.get("AIRTABLE_ENABLED", "").lower() != "true":
        return None
    api_key = os.environ.get("AIRTABLE_API_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    table = os.environ.get("AIRTABLE_LEADS_TABLE", "Leads")
    if not (api_key and base_id):
        return None
    try:
        _singleton = LeadsAirtableService(api_key, base_id, table)
        log.info("Leads service: initialized against '%s'", table)
        return _singleton
    except Exception:
        log.exception("Leads service init failed")
        return None


def reset_leads_service() -> None:
    global _singleton
    _singleton = None
