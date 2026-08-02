"""Leads-table service for the Next Best Action panel.

Independent of the Opportunities service. Reads the `Leads` table on the same
Airtable base, uses a schema-driven field map (never renames Airtable fields),
and enforces a strict write allowlist for approve / hold / do-not-contact /
message-edit actions.

Safety model:
- Every approval is gated server-side by `services.outreach_policy`. The UI
  cannot approve a lead the policy rejects, because the UI is not what decides.
- Duplicate leads are grouped by `services.dedupe`; only the canonical record of
  a group is actionable, so the same homeowner cannot be messaged twice from two
  cards.
- Approvals are idempotent and audited via `services.audit`.
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

from services import dedupe
from services.audit import derive_idempotency_key, get_audit_log
from services.field_norm import clean_text, is_valid_email, is_valid_phone
from services.outreach_policy import (
    EligibilityResult,
    PolicyThresholds,
    computed_readiness,
    evaluate,
)

log = logging.getLogger("bloodhound.leads")


# Exact Airtable field name (case-sensitive) -> internal snake_case key.
LEADS_FIELD_MAP: Dict[str, str] = {
    "Leads Name": "name",
    "Business name": "business_name",
    "Opportunity type": "opportunity_type",
    "Source": "source",
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
    # Read by the eligibility policy and the dedupe fingerprint. Advisory AI
    # prose is namespaced at the API boundary, never treated as live state.
    "Risk flags": "risk_flags",
    "Missing information": "missing_information",
    "Permit number": "permit_number",
    "Confidence score": "confidence_score",
}

# Only these Airtable fields may ever be written by this service.
EDITABLE_FIELDS = {
    "Approval status",
    "Outreach status",
    "Status",
    "First message",
}

# Case-insensitive substring match — any lead whose Status / Outreach status /
# Approval status contains one of these is excluded from the action queue.
EXCLUDE_TOKENS = ("duplicate", "do not contact", "sent", "closed", "complete")

PRIORITY_RANK = {"urgent": 4, "high": 3, "medium": 2, "normal": 2, "low": 1}

# Written on approve. Must exist as options on the Airtable single-selects.
APPROVED_VALUE = "Approved"

# Tried in order when reverting an approval. Airtable rejects a single-select
# value that is not a configured option, so we degrade through plausible
# vocabulary before clearing the cell outright.
REVERT_CANDIDATES = ("Pending", "Pending Approval", "Needs Review", "Not Approved", None)


class OutreachBlocked(Exception):
    """Raised when a write is refused by the outreach policy.

    Carries the structured result so the API layer can return the blocking
    reasons rather than a bare 4xx.
    """

    def __init__(self, result: EligibilityResult):
        self.result = result
        blockers = "; ".join(f.message for f in result.blockers) or "not eligible"
        super().__init__(blockers)


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
        self._duplicate_index: Dict[str, Any] = {"by_record": {}, "groups": {}}
        self._last_refresh: float = 0.0
        self._field_map: Dict[str, str] = {}
        self._schema_field_names: List[str] = []
        # Per-process session state — reset on backend restart.
        self._skipped: set = set()
        self._held: set = set()
        self._approvals: Dict[str, str] = {}
        self._audit = get_audit_log()
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
        self._schema_field_names = sorted(available)
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
        index = dedupe.annotate(list(new_cache.values()))
        with self._lock:
            self._cache = new_cache
            self._duplicate_index = index
            self._last_refresh = now

    def _record_to_dto(self, record: Dict[str, Any]) -> Dict[str, Any]:
        fields = record.get("fields", {}) or {}
        dto: Dict[str, Any] = {
            "id": record.get("id"),
            "created_time": record.get("createdTime"),
        }
        for at_name, snake in self._field_map.items():
            dto[snake] = fields.get(at_name)
        # Guarantee every mapped key exists so the UI never reads undefined.
        for snake in LEADS_FIELD_MAP.values():
            dto.setdefault(snake, None)
        # Compose a stable Airtable URL for "Open Full Lead"
        if self._table_id and dto["id"]:
            dto["_airtable_url"] = f"https://airtable.com/{self._base_id}/{self._table_id}/{dto['id']}"
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

    def duplicates_report(self) -> Dict[str, Any]:
        self._refresh_cache()
        with self._lock:
            index = deepcopy(self._duplicate_index)
        return dedupe.duplicate_report(index)

    # ---------- eligibility ----------
    def eligibility(self, lead: Dict[str, Any]) -> EligibilityResult:
        """Evaluate the outreach policy against a lead DTO."""
        return evaluate(lead, thresholds=PolicyThresholds.from_env(),
                        duplicate_of=lead.get("duplicate_of"))

    def eligibility_for_id(self, lead_id: str) -> Optional[EligibilityResult]:
        lead = self.get(lead_id)
        return self.eligibility(lead) if lead else None

    def readiness(self, lead_id: str) -> Optional[Dict[str, Any]]:
        """Live-field readiness for the detail view (fix: no stale AI prose)."""
        lead = self.get(lead_id)
        if not lead:
            return None
        return computed_readiness(lead, duplicate_of=lead.get("duplicate_of"))

    # ---------- selection logic ----------
    def _is_excluded(self, lead: Dict[str, Any]) -> bool:
        if lead["id"] in self._held:
            return True
        if lead.get("job_won") is True:
            return True
        # A suppressed duplicate is never independently actionable — the
        # canonical member of its group carries the action.
        if lead.get("duplicate_of"):
            return True
        # A lead is not actionable without a name AND a recommended next action.
        # Empty/skeleton rows in Airtable must never surface as the NBA.
        name = clean_text(lead.get("name"))
        next_action = clean_text(lead.get("next_action"))
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
        """A contact is usable only if it is syntactically reachable.

        The `Verified opportunity` / `Contact found` checkboxes used to count
        here, which let a lead with no phone and no email look contactable.
        """
        return (
            is_valid_phone(lead.get("contact_phone"))
            or is_valid_phone(lead.get("phone_number"))
            or is_valid_email(lead.get("contact_email"))
            or is_valid_email(lead.get("email"))
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

    def _explain(self, lead: Dict[str, Any], result: EligibilityResult) -> str:
        """Why this lead surfaced — stated from live field values, not from the
        AI's stored narrative."""
        parts: List[str] = [f"score {result.score:g} ({result.score_source.replace('_', ' ')})"]
        if result.recipient.channel:
            parts.append(f"reachable by {result.recipient.channel}")
        if result.recipient.counterparty:
            parts.append(f"contact {result.recipient.counterparty}")
        if lead.get("opportunity_type"):
            parts.append(str(lead["opportunity_type"]).lower())
        if lead.get("source"):
            parts.append(f"from {lead['source']}")
        if not result.eligible:
            parts.append(f"{len(result.blockers)} blocker(s)")
        return " · ".join(parts)

    def pick_next_best_action(self) -> Optional[Dict[str, Any]]:
        candidates = [
            l for l in self.all()
            if not self._is_excluded(l) and l["id"] not in self._skipped
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda l: (
            -self._completeness(l),
            -int(self._ai_complete(l)),
            -int(self._has_usable_contact(l)),
            -self._priority_rank(l.get("priority")),
            -(l.get("lead_score") or 0),
            (l.get("date_discovered") or l.get("created_time") or ""),
        ))
        pick = candidates[0]
        result = self.eligibility(pick)
        pick["_eligibility"] = result.to_dict()
        pick["_readiness"] = computed_readiness(pick, duplicate_of=pick.get("duplicate_of"))
        pick["_selection_reason"] = self._explain(pick, result)
        if pick["id"] in self._approvals:
            pick["_approved_at"] = self._approvals[pick["id"]]
        return pick

    def queue_stats(self) -> Dict[str, int]:
        leads = self.all()
        queued = [l for l in leads
                  if not self._is_excluded(l) and l["id"] not in self._skipped]
        approvable = sum(1 for l in queued if self.eligibility(l).eligible)
        return {
            "total": len(leads),
            "eligible": len(queued),
            "approvable": approvable,
            "blocked_by_policy": len(queued) - approvable,
            "duplicates_suppressed": sum(1 for l in leads if l.get("duplicate_of")),
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

    def approve(self, lead_id: str,
                idempotency_key: Optional[str] = None,
                actor: Optional[str] = None,
                acknowledged_warnings: Optional[List[str]] = None) -> Dict[str, Any]:
        """Approve a lead for outreach.

        Refuses with `OutreachBlocked` unless the policy passes. Idempotent: a
        replay of the same key returns the original response instead of writing
        to Airtable again.
        """
        lead = self.get(lead_id)
        if lead is None:
            raise KeyError(lead_id)

        key = idempotency_key or derive_idempotency_key("approve", lead_id)
        replay = self._audit.idempotency.get(key)
        if replay is not None:
            self._audit.record(
                action="approve", entity_id=lead_id, outcome="replayed",
                actor=actor, idempotency_key=key,
                reason="Idempotency key already processed — no write performed.",
            )
            return {**replay, "replayed": True}

        result = self.eligibility(lead)
        if not result.eligible:
            self._audit.record(
                action="approve", entity_id=lead_id, outcome="rejected",
                actor=actor, idempotency_key=key,
                reason="Blocked by outreach policy.",
                eligibility=result.to_dict(),
            )
            raise OutreachBlocked(result)

        ts = datetime.now(timezone.utc).isoformat()
        wrote_approval = self._safe_update(lead_id, "Approval status", APPROVED_VALUE)
        wrote_outreach = self._safe_update(lead_id, "Outreach status", APPROVED_VALUE)
        self._approvals[lead_id] = ts
        self._refresh_cache(force=True)

        response = {
            "lead_id": lead_id,
            "state": "approved",
            "approved_at": ts,
            "idempotency_key": key,
            "persisted": {"Approval status": wrote_approval,
                          "Outreach status": wrote_outreach},
            "recipient": result.to_dict()["recipient"],
            "acknowledged_warnings": acknowledged_warnings or [],
            "revertible": wrote_approval or wrote_outreach,
            "note": ("Approved — no message has been sent. Dispatch is not yet "
                     "connected; see docs/INTEGRATIONS.md."),
        }
        self._audit.idempotency.put(key, response)
        self._audit.record(
            action="approve", entity_id=lead_id, outcome="accepted",
            actor=actor, idempotency_key=key,
            eligibility=result.to_dict(),
            changes={"Approval status": APPROVED_VALUE, "Outreach status": APPROVED_VALUE},
            metadata={"persisted": response["persisted"],
                      "acknowledged_warnings": acknowledged_warnings or []},
        )
        return response

    def revert_approval(self, lead_id: str,
                        actor: Optional[str] = None,
                        reason: Optional[str] = None) -> Dict[str, Any]:
        """Undo an approval.

        Safe because approval only sets two allowlisted status columns and never
        dispatches a message — there is nothing sent to recall. Clears the
        idempotency entry so the lead can be deliberately re-approved.
        """
        lead = self.get(lead_id)
        if lead is None:
            raise KeyError(lead_id)

        reverted_to: Optional[str] = None
        persisted: Dict[str, Any] = {}
        for candidate in REVERT_CANDIDATES:
            if self._safe_update(lead_id, "Approval status", candidate):
                reverted_to = candidate
                persisted["Approval status"] = candidate
                break
        if reverted_to is not None:
            if self._safe_update(lead_id, "Outreach status", reverted_to):
                persisted["Outreach status"] = reverted_to

        self._approvals.pop(lead_id, None)
        self._audit.idempotency.invalidate(derive_idempotency_key("approve", lead_id))
        self._refresh_cache(force=True)

        response = {
            "lead_id": lead_id,
            "state": "approval_reverted",
            "reverted_to": reverted_to,
            "persisted": persisted,
            "note": ("Approval withdrawn. No message had been dispatched."
                     if persisted else
                     "Session approval cleared, but no Airtable status field was writable."),
        }
        self._audit.record(
            action="revert_approval", entity_id=lead_id,
            outcome="accepted" if persisted else "error",
            actor=actor, reason=reason, changes=persisted,
        )
        return response

    def hold(self, lead_id: str, actor: Optional[str] = None) -> Dict[str, Any]:
        self._held.add(lead_id)
        wrote = self._safe_update(lead_id, "Outreach status", "Hold")
        self._refresh_cache(force=True)
        self._audit.record(action="hold", entity_id=lead_id, outcome="accepted",
                           actor=actor, changes={"Outreach status": "Hold"} if wrote else {})
        return {"lead_id": lead_id, "state": "hold", "persisted": wrote}

    def skip(self, lead_id: str, actor: Optional[str] = None) -> Dict[str, Any]:
        self._skipped.add(lead_id)
        self._audit.record(action="skip", entity_id=lead_id, outcome="accepted",
                           actor=actor, reason="Session-only skip; nothing written.")
        return {"lead_id": lead_id, "state": "skipped"}

    def do_not_contact(self, lead_id: str, actor: Optional[str] = None) -> Dict[str, Any]:
        # Prefer Status; if unwritable/absent, try Outreach status; then Approval status.
        for field in ("Status", "Outreach status", "Approval status"):
            if self._safe_update(lead_id, field, "Do Not Contact"):
                self._refresh_cache(force=True)
                self._audit.record(action="do_not_contact", entity_id=lead_id,
                                   outcome="accepted", actor=actor,
                                   changes={field: "Do Not Contact"})
                return {"lead_id": lead_id, "state": "do_not_contact", "persisted_to": field}
        # Fallback: session-only exclude
        self._held.add(lead_id)
        self._audit.record(action="do_not_contact", entity_id=lead_id, outcome="error",
                           actor=actor,
                           reason="No writable status field; suppressed in session only.")
        return {"lead_id": lead_id, "state": "do_not_contact", "persisted_to": None,
                "note": "Session-only (no writable Status field found)"}

    def update_message(self, lead_id: str, message: str,
                       actor: Optional[str] = None) -> Optional[Dict[str, Any]]:
        previous = (self.get(lead_id) or {}).get("first_message")
        if not self._safe_update(lead_id, "First message", message):
            return None
        self._refresh_cache(force=True)
        self._audit.record(action="update_message", entity_id=lead_id,
                           outcome="accepted", actor=actor,
                           changes={"First message": {"from": previous, "to": message}})
        return self.get(lead_id)


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
