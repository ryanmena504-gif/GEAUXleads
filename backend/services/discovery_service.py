"""
Discovery services — thin readers for the "discovery queue" Airtable tables
that live outside the governed Leads pipeline.

These tables (Property Manager Discovery Queue, Real Estate Agent Outreach,
Investor Intelligence, etc.) are owned by Claude + Make on the data side.
Bloodhound is strictly a read-only viewer. No writes.

Rather than duplicate the full AirtableOpportunityService (schema loading,
write allowlist, field maps), each discovery reader:
  • Reads every field on every record as-is
  • Applies snake_case normalization to the field names for the API layer
  • Caches for a short TTL (60s) so we don't hammer the API
  • Falls back to an empty list if the table doesn't exist or errors out
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pyairtable import Api

log = logging.getLogger("bloodhound.discovery")


# ---------------------------------------------------------------------------
# ZIP → New Orleans neighborhood map. Rough grouping — a single ZIP often
# covers multiple neighborhoods, so we pick the most recognized label per
# code. Out-of-parish ZIPs get their municipality name so nothing renders
# blank on Ryan's Louisiana list.
# ---------------------------------------------------------------------------
_ZIP_TO_NEIGHBORHOOD: Dict[str, str] = {
    # Orleans Parish
    "70112": "French Quarter / CBD",
    "70113": "Central City",
    "70114": "Algiers Point",
    "70115": "Uptown / Garden District",
    "70116": "Marigny / Tremé",
    "70117": "Bywater / 9th Ward",
    "70118": "Carrollton / Uptown",
    "70119": "Mid-City / Bayou St. John",
    "70122": "Gentilly",
    "70124": "Lakeview / Lakefront",
    "70125": "Broadmoor / Zion City",
    "70126": "New Orleans East",
    "70127": "New Orleans East",
    "70128": "New Orleans East",
    "70129": "New Orleans East",
    "70130": "Warehouse District / Lower Garden",
    "70131": "Algiers / English Turn",
    # Nearby Jefferson / Plaquemines / St. Bernard
    "70001": "Metairie",
    "70002": "Metairie",
    "70003": "Metairie",
    "70005": "Old Metairie",
    "70006": "Metairie",
    "70037": "Belle Chasse",
    "70043": "Chalmette",
    "70058": "Gretna",
    "70062": "Kenner",
    "70065": "Kenner",
    "70072": "Marrero",
    "70094": "Westwego",
    "70121": "Jefferson / Riverbend",
    "70122-9998": "Gentilly",
    "70123": "Elmwood / Harahan",
}


def zip_to_neighborhood(zipcode: Optional[str]) -> Optional[str]:
    if not zipcode:
        return None
    z = str(zipcode).strip()
    m = re.match(r"^(\d{5})", z)
    if not m:
        return None
    return _ZIP_TO_NEIGHBORHOOD.get(m.group(1))


def extract_zip(address: Any) -> Optional[str]:
    if not address:
        return None
    m = re.search(r"\b(\d{5})(?:-\d{4})?\b", str(address))
    return m.group(1) if m else None


def days_on_table(created_time: Optional[str]) -> Optional[int]:
    """Whole days between record creation and now. Uses Airtable's
    `createdTime` metadata. Returns None if unparseable."""
    if not created_time:
        return None
    try:
        # Airtable returns ISO-8601 with a trailing Z; normalize to +00:00.
        s = str(created_time).replace("Z", "+00:00")
        created = datetime.fromisoformat(s)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - created
        return max(0, delta.days)
    except (ValueError, TypeError):
        return None


def _snake(name: str) -> str:
    """Airtable field name → snake_case key for the API layer."""
    s = re.sub(r"[^\w\s]", "", name or "").strip().replace(" ", "_")
    return s.lower()


class DiscoveryReader:
    """Read-only reader for one Airtable table. Zero writes."""

    def __init__(self, api_key: str, base_id: str, table_name: str, cache_ttl: float = 60.0):
        self._api = Api(api_key)
        self._base_id = base_id
        self._table_name = table_name
        self._table = self._api.table(base_id, table_name)
        self._cache_ttl = cache_ttl
        self._lock = threading.Lock()
        self._cache: List[Dict[str, Any]] = []
        self._last_refresh: float = 0.0
        self._last_error: Optional[str] = None

    def _record_to_dict(self, record: Dict[str, Any]) -> Dict[str, Any]:
        raw = record.get("fields", {}) or {}
        out: Dict[str, Any] = {
            "id": record.get("id"),
            "created_time": record.get("createdTime"),
        }
        for name, value in raw.items():
            out[_snake(name)] = value
        # Also keep the raw Airtable-named field dict for the DebugPanel style
        # views (never used for governed logic — read-only inspection only).
        out["_raw"] = dict(raw)
        return out

    def _needs_refresh(self) -> bool:
        return (time.time() - self._last_refresh) > self._cache_ttl

    def all(self) -> List[Dict[str, Any]]:
        with self._lock:
            if not self._needs_refresh():
                return list(self._cache)
        # Do the refresh outside the lock to avoid blocking readers.
        try:
            records = self._table.all()
            items = [self._record_to_dict(r) for r in records]
            with self._lock:
                self._cache = items
                self._last_refresh = time.time()
                self._last_error = None
            log.info("Discovery '%s': loaded %d records", self._table_name, len(items))
            return list(items)
        except Exception as e:  # noqa: BLE001
            log.warning("Discovery '%s' fetch failed: %s", self._table_name, e)
            with self._lock:
                self._last_error = str(e)[:220]
                return list(self._cache)  # stale beats nothing

    def patch_fields(
        self, record_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Patch a small allowlist of fields on a discovery record.

        Callers pass Airtable-column-named keys (e.g. `"Email"`,
        `"Phone"`) — NOT snake-cased keys. Only used by the Auto-fill
        Contact flow on the RE agents page. All other Discovery surfaces
        remain strictly read-only.

        Invalidates this reader's cache on success so the next `all()`
        call fetches fresh data.
        """
        if not record_id:
            raise ValueError("record_id is required")
        if not updates:
            raise ValueError("updates must not be empty")
        try:
            updated = self._table.update(record_id, updates)
        except Exception as e:  # noqa: BLE001
            msg = str(e)[:280]
            log.warning(
                "Discovery '%s' patch failed for %s: %s",
                self._table_name,
                record_id,
                msg,
            )
            raise RuntimeError(f"Airtable patch failed: {msg}") from e
        with self._lock:
            # Force refresh next .all()
            self._last_refresh = 0.0
        return self._record_to_dict(updated)


# ---------------------------------------------------------------------------
# Property Manager Discovery Queue
# ---------------------------------------------------------------------------
# The Airtable base has a table named "Property Manager Discovery Queue" with
# 23 property management companies. Each has a `Review Status` field with one
# of: "New" / "Worth a look" / "Not relevant …" / "Promoted to Leads".
# Only "Worth a look" records surface as real candidates on the Discovery UI.
# Everything else is filtered out unless the caller passes status="all".
# ---------------------------------------------------------------------------
PROPERTY_MANAGER_TABLE = "Property Manager Discovery Queue"

_pm_reader: Optional[DiscoveryReader] = None


def get_property_manager_reader() -> Optional[DiscoveryReader]:
    """Lazy singleton — returns None if Airtable isn't configured."""
    global _pm_reader
    if _pm_reader is not None:
        return _pm_reader
    api_key = os.environ.get("AIRTABLE_API_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    enabled = os.environ.get("AIRTABLE_ENABLED", "").lower() == "true"
    if not (enabled and api_key and base_id):
        return None
    _pm_reader = DiscoveryReader(api_key, base_id, PROPERTY_MANAGER_TABLE)
    return _pm_reader


# Review-Status values Claude ships (per user handoff).
REVIEW_STATUS_WORTH_A_LOOK = "worth a look"
REVIEW_STATUS_PROMOTED = "promoted to leads"


def _normalize_status(v: Any) -> str:
    return (str(v or "").strip().lower())


def _pick_first(row: Dict[str, Any], keys: List[str]) -> Any:
    """Return the first non-empty value from a candidate key list.

    The Property Manager table's field names aren't fully locked, so we look
    for a few common variants (case-insensitive after _snake) and take the
    first one that has a value. Never invents data — if none match, returns None.
    """
    for k in keys:
        v = row.get(k)
        if v not in (None, "", [], {}):
            return v
    return None


def list_property_managers(status: str = "worth_a_look") -> List[Dict[str, Any]]:
    """Return the property manager discovery queue, filtered by review status.

    status: "worth_a_look" (default) | "all" | any exact Review Status value
    """
    reader = get_property_manager_reader()
    if reader is None:
        return []
    rows = reader.all()

    if status != "all":
        wanted = _normalize_status(status.replace("_", " "))
        rows = [r for r in rows if _normalize_status(r.get("review_status")) == wanted]

    # Sort: fresh records first (uses Airtable's createdTime metadata), then id.
    rows.sort(key=lambda r: (r.get("created_time") or "", r.get("id") or ""), reverse=True)

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            "id": r.get("id"),
            "name": _pick_first(r, ["business_name", "name", "company_name", "company", "property_manager", "property_management_company"]),
            "phone": _pick_first(r, ["phone", "phone_number", "contact_phone", "main_phone"]),
            "website": _pick_first(r, ["website", "url", "web", "homepage"]),
            "email": _pick_first(r, ["email", "contact_email"]),
            "address": _pick_first(r, ["address", "office_address", "location"]),
            "notes": _pick_first(r, ["notes", "note", "why", "context", "why_worth_a_look", "why_it_matters"]),
            "portfolio_size": _pick_first(r, ["portfolio_size", "units", "portfolio", "unit_count"]),
            "review_status": r.get("review_status"),
            "date_discovered": r.get("date_discovered"),
            "created_time": r.get("created_time"),
            "days_on_table": days_on_table(r.get("created_time")),
            "neighborhood": zip_to_neighborhood(extract_zip(_pick_first(r, ["address", "office_address", "location"]))),
        })
    return out


def property_manager_status_counts() -> Dict[str, int]:
    """Count records per Review Status — used to render tab badges."""
    reader = get_property_manager_reader()
    if reader is None:
        return {}
    counts: Dict[str, int] = {}
    for r in reader.all():
        raw_status = r.get("review_status") or "Unset"
        label = raw_status if isinstance(raw_status, str) else str(raw_status)
        counts[label] = counts.get(label, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Real Estate Agent Outreach
# ---------------------------------------------------------------------------
# 10 curated real-estate agents for a pre-listing "photo-ready bathroom"
# pitch. None have verified contact info yet — Contact Enrichment Status
# is uniformly "Needs Public Contact" and Outreach Gate is uniformly
# "Locked — no outreach". Bloodhound respects the gate: no mailto/sms
# button renders while an agent is locked. When Make flips the gate to
# an unlocked value, the pitch buttons light up automatically.
# ---------------------------------------------------------------------------
REAL_ESTATE_AGENT_TABLE = "Real Estate Agent Outreach"

_agent_reader: Optional[DiscoveryReader] = None


def get_real_estate_agent_reader() -> Optional[DiscoveryReader]:
    global _agent_reader
    if _agent_reader is not None:
        return _agent_reader
    api_key = os.environ.get("AIRTABLE_API_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    enabled = os.environ.get("AIRTABLE_ENABLED", "").lower() == "true"
    if not (enabled and api_key and base_id):
        return None
    _agent_reader = DiscoveryReader(api_key, base_id, REAL_ESTATE_AGENT_TABLE)
    return _agent_reader


# An agent is "outreach ready" ONLY when the governed Outreach Gate is
# set to one of an explicit allowlist of "cleared" values. Anything else
# — empty, unknown, "Needs approval", "Review pending", etc. — is
# treated as LOCKED. This preserves the hard contract that Bloodhound
# never surfaces a live outreach button unless Claude/Make cleared the
# lead by name.
_UNLOCKED_GATE_VALUES = frozenset({
    "ready",
    "cleared",
    "unlocked",
    "outreach ready",
    "ready to pitch",
    "approved",
    "ready to contact",
    "outreach cleared",
    "gate cleared",
    "open",
})


def _is_outreach_ready(gate: Any) -> bool:
    if not gate:
        return False
    g = str(gate).strip().lower()
    return g in _UNLOCKED_GATE_VALUES


def list_real_estate_agents(status: str = "all") -> List[Dict[str, Any]]:
    """Return the real estate agent outreach queue.

    status:
      • "all" (default) — every agent
      • "ready" — only agents with Outreach Gate unlocked
      • "locked" — only gated agents
    """
    reader = get_real_estate_agent_reader()
    if reader is None:
        return []
    rows = reader.all()

    if status == "ready":
        rows = [r for r in rows if _is_outreach_ready(r.get("outreach_gate"))]
    elif status == "locked":
        rows = [r for r in rows if not _is_outreach_ready(r.get("outreach_gate"))]

    rows.sort(key=lambda r: (r.get("created_time") or "", r.get("id") or ""), reverse=True)

    out: List[Dict[str, Any]] = []
    for r in rows:
        gate = r.get("outreach_gate")
        out.append({
            "id": r.get("id"),
            "name": _pick_first(r, ["agent_name", "name", "full_name"]),
            "brokerage": _pick_first(r, ["brokerage", "firm", "agency", "company"]),
            "why_target": _pick_first(r, ["why_theyre_a_target", "why", "why_target", "target_reason", "target_notes"]),
            "phone": _pick_first(r, ["public_business_phone", "phone", "phone_number", "contact_phone"]),
            "email": _pick_first(r, ["public_business_email", "email", "contact_email"]),
            "website": _pick_first(r, ["website", "url", "profile_url"]),
            "outreach_gate": gate,
            "contact_enrichment_status": _pick_first(r, ["contact_enrichment_status", "enrichment_status"]),
            "outreach_ready": _is_outreach_ready(gate),
            "created_time": r.get("created_time"),
            "days_on_table": days_on_table(r.get("created_time")),
        })
    return out


def real_estate_agent_status_counts() -> Dict[str, int]:
    reader = get_real_estate_agent_reader()
    if reader is None:
        return {}
    total = 0
    ready = 0
    for r in reader.all():
        total += 1
        if _is_outreach_ready(r.get("outreach_gate")):
            ready += 1
    return {"all": total, "ready": ready, "locked": total - ready}


# Column names on the Real Estate Agent Outreach table for the
# Auto-fill Contact flow. Bloodhound writes ONLY to these two columns —
# never to Outreach Gate, Contact Enrichment Status, or anything else
# governed by Claude/Make. The names below match the exact Airtable
# columns already present on the table (verified 2026-02-18):
#   'Public Business Email' and 'Public Business Phone'.
# The `patch_fields` method has an auto-create safety net if those
# columns get renamed or dropped — so this stays a one-tap flow no
# matter what changes on the Airtable side.
_RE_AGENT_EMAIL_COL = "Public Business Email"
_RE_AGENT_PHONE_COL = "Public Business Phone"


def enrich_real_estate_agent(
    record_id: str, email: Optional[str] = None, phone: Optional[str] = None
) -> Dict[str, Any]:
    """Write a verified email and/or phone onto an agent row. Returns
    the refreshed DTO (same shape as `list_real_estate_agents` items).
    Raises RuntimeError with a human-readable message on failure."""
    reader = get_real_estate_agent_reader()
    if reader is None:
        raise RuntimeError("Real Estate Agent Outreach table is not configured")
    email = (email or "").strip() or None
    phone = (phone or "").strip() or None
    if not email and not phone:
        raise ValueError("At least one of email or phone is required")

    updates: Dict[str, Any] = {}
    if email:
        updates[_RE_AGENT_EMAIL_COL] = email
    if phone:
        updates[_RE_AGENT_PHONE_COL] = phone

    patched = reader.patch_fields(record_id, updates)

    # Return a DTO that matches list_real_estate_agents' shape so the
    # frontend can drop it into the row without another round-trip.
    gate = patched.get("outreach_gate")
    return {
        "id": patched.get("id"),
        "name": _pick_first(patched, ["agent_name", "name", "full_name"]),
        "brokerage": _pick_first(patched, ["brokerage", "firm", "agency", "company"]),
        "why_target": _pick_first(patched, ["why_theyre_a_target", "why", "why_target", "target_reason", "target_notes"]),
        "phone": _pick_first(patched, ["public_business_phone", "phone", "phone_number", "contact_phone"]),
        "email": _pick_first(patched, ["public_business_email", "email", "contact_email"]),
        "website": _pick_first(patched, ["website", "url", "profile_url"]),
        "outreach_gate": gate,
        "contact_enrichment_status": _pick_first(patched, ["contact_enrichment_status", "enrichment_status"]),
        "outreach_ready": _is_outreach_ready(gate),
        "created_time": patched.get("created_time"),
        "days_on_table": days_on_table(patched.get("created_time")),
    }


# ---------------------------------------------------------------------------
# Landlords — STR license commercial owners
# ---------------------------------------------------------------------------
# 63 property owners sourced from the New Orleans Commercial Short-Term
# Rental license registry. Contact enrichment is a known gap (no phone,
# no email yet) — Ryan's play here is mail-only. The Discovery UI groups
# them, lets him pick a batch, and renders a printable multi-page letter
# spread that opens the browser's native print dialog.
# ---------------------------------------------------------------------------
LANDLORDS_TABLE = "Landlords"

_landlord_reader: Optional[DiscoveryReader] = None


def get_landlord_reader() -> Optional[DiscoveryReader]:
    global _landlord_reader
    if _landlord_reader is not None:
        return _landlord_reader
    api_key = os.environ.get("AIRTABLE_API_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    enabled = os.environ.get("AIRTABLE_ENABLED", "").lower() == "true"
    if not (enabled and api_key and base_id):
        return None
    _landlord_reader = DiscoveryReader(api_key, base_id, LANDLORDS_TABLE)
    return _landlord_reader


def list_landlords(status: str = "not_contacted", ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Return STR-license landlords.

    status:
      • "not_contacted" (default) — Outreach Status is empty or "Not Contacted"
      • "contacted" — anything else
      • "all" — every record
    ids: if provided, return only records with these Airtable ids (for the
         print-letter route, which needs to pull an exact selection).
    """
    reader = get_landlord_reader()
    if reader is None:
        return []
    rows = reader.all()

    if ids:
        wanted = set(ids)
        rows = [r for r in rows if r.get("id") in wanted]
    elif status == "not_contacted":
        rows = [r for r in rows if _normalize_status(r.get("outreach_status")) in ("", "not contacted")]
    elif status == "contacted":
        rows = [r for r in rows if _normalize_status(r.get("outreach_status")) not in ("", "not contacted")]

    rows.sort(key=lambda r: (
        _normalize_status(r.get("owner_name")),
        r.get("id") or "",
    ))

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            "id": r.get("id"),
            "owner_name": _pick_first(r, ["owner_name", "owner", "name", "landlord_name"]),
            "property_address": _pick_first(r, ["property_address", "address", "street_address"]),
            "mailing_address": _pick_first(r, ["mailing_address", "owner_mailing_address", "correspondence_address"]),
            "license_number": _pick_first(r, ["license_number", "license", "str_license"]),
            "license_expiration": _pick_first(r, ["license_expiration", "expiration", "expires"]),
            "outreach_gate": r.get("outreach_gate"),
            "outreach_status": r.get("outreach_status"),
            "source": r.get("source"),
            "created_time": r.get("created_time"),
            "days_on_table": days_on_table(r.get("created_time")),
            "zip": extract_zip(_pick_first(r, ["property_address", "mailing_address", "address"])),
            "neighborhood": zip_to_neighborhood(
                extract_zip(_pick_first(r, ["property_address", "mailing_address", "address"]))
            ),
        })
    return out


def landlord_status_counts() -> Dict[str, int]:
    reader = get_landlord_reader()
    if reader is None:
        return {}
    total = 0
    not_contacted = 0
    for r in reader.all():
        total += 1
        if _normalize_status(r.get("outreach_status")) in ("", "not contacted"):
            not_contacted += 1
    return {
        "all": total,
        "not_contacted": not_contacted,
        "contacted": total - not_contacted,
    }


# ---------------------------------------------------------------------------
# Investor Intelligence
# ---------------------------------------------------------------------------
# Real estate investors / LLC entities tracking multi-property portfolios.
# Mirrors the Partner Intelligence structure conceptually. Bloodhound is
# strictly a read-only viewer — Claude + Make own record creation and
# classification on the Airtable side.
# ---------------------------------------------------------------------------
INVESTORS_TABLE = "Investor Intelligence"

_investor_reader: Optional[DiscoveryReader] = None


def get_investor_reader() -> Optional[DiscoveryReader]:
    global _investor_reader
    if _investor_reader is not None:
        return _investor_reader
    api_key = os.environ.get("AIRTABLE_API_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    enabled = os.environ.get("AIRTABLE_ENABLED", "").lower() == "true"
    if not (enabled and api_key and base_id):
        return None
    _investor_reader = DiscoveryReader(api_key, base_id, INVESTORS_TABLE)
    return _investor_reader


def list_investors(status: str = "all") -> List[Dict[str, Any]]:
    """Return investor intelligence records.

    status:
      • "all" (default) — every record
      • "ready" — Outreach Gate unlocked
      • "locked" — Outreach Gate held
    """
    reader = get_investor_reader()
    if reader is None:
        return []
    rows = reader.all()

    if status == "ready":
        rows = [r for r in rows if _is_outreach_ready(r.get("outreach_gate"))]
    elif status == "locked":
        rows = [r for r in rows if not _is_outreach_ready(r.get("outreach_gate"))]

    rows.sort(key=lambda r: (r.get("created_time") or "", r.get("id") or ""), reverse=True)

    out: List[Dict[str, Any]] = []
    for r in rows:
        gate = r.get("outreach_gate")
        out.append({
            "id": r.get("id"),
            "name": _pick_first(r, [
                "investorllc_name",         # "Investor/LLC Name" after _snake
                "investor_name",
                "name",
                "entity_name",
                "llc_name",
                "company_name",
            ]),
            "entity_type": _pick_first(r, ["investor_type", "entity_type", "type", "llc_type"]),
            "portfolio_size": _pick_first(r, [
                "observed_property_count", "portfolio_size", "units",
                "property_count", "portfolio",
            ]),
            "portfolio_value": _pick_first(r, ["portfolio_value", "total_value", "estimated_value"]),
            "score": _pick_first(r, ["investor_score", "score", "priority_score"]),
            "confidence": r.get("confidence"),
            "relationship_status": r.get("relationship_status"),
            "why_target": _pick_first(r, [
                "evidence_summary", "why_theyre_a_target", "why", "why_target",
                "target_reason", "target_notes", "notes",
            ]),
            "recommended_next_move": _pick_first(r, ["recommended_next_move", "next_move", "recommendation"]),
            "principal": _pick_first(r, ["principal", "principal_name", "primary_contact", "contact_name"]),
            "phone": _pick_first(r, [
                "public_business_phone", "phone", "phone_number", "contact_phone",
            ]),
            "email": _pick_first(r, ["public_business_email", "email", "contact_email"]),
            "website": _pick_first(r, ["public_contact_source", "website", "url"]),
            "address": _pick_first(r, ["address", "office_address", "location", "mailing_address"]),
            "service_area": r.get("service_area"),
            "outreach_gate": gate,
            "outreach_status": r.get("outreach_status"),
            "contact_enrichment_status": _pick_first(r, ["contact_enrichment_status", "enrichment_status"]),
            "outreach_ready": _is_outreach_ready(gate),
            "created_time": r.get("created_time"),
            "days_on_table": days_on_table(r.get("created_time")),
            "neighborhood": zip_to_neighborhood(
                extract_zip(_pick_first(r, ["address", "office_address", "location", "mailing_address"]))
            ),
        })
    return out


def investor_status_counts() -> Dict[str, int]:
    reader = get_investor_reader()
    if reader is None:
        return {}
    total = 0
    ready = 0
    for r in reader.all():
        total += 1
        if _is_outreach_ready(r.get("outreach_gate")):
            ready += 1
    return {"all": total, "ready": ready, "locked": total - ready}
