"""
Spreadsheet-safe CSV builder. Per-feed whitelist prevents accidental
export of secrets, raw provider payloads, or unmapped internals.
Formula-injection guard prefixes any cell starting with =+-@|\\t\\r with '.
"""
from __future__ import annotations
import csv, io
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

# Per-feed export whitelists. Any field not listed here is NEVER written
# to the CSV, even if the DTO carries it. Never includes `_raw`,
# `raw_source_data`, provider payloads, or credentials.
FEED_WHITELIST: Dict[str, List[str]] = {
    "leads": [
        "id", "name", "status", "current_queue", "contact_readiness",
        "money_signal", "governed_priority_score", "score_basis",
        "priority_explanation", "project_address", "project_type",
        "decision_maker", "email", "phone", "source", "source_url",
        "permit_number", "permit_filing_date", "estimated_value",
        "created_time", "days_on_table", "next_follow_up",
    ],
    "property_managers": [
        "id", "name", "website", "email", "phone", "neighborhood",
        "review_status", "created_time", "days_on_table",
    ],
    "re_agents": [
        "id", "name", "brokerage", "email", "phone", "why_target",
        "outreach_gate", "contact_enrichment_status",
        "created_time", "days_on_table",
    ],
    "landlords": [
        "id", "owner_name", "property_address", "mailing_address",
        "license_number", "license_expiration", "neighborhood",
        "outreach_status", "created_time", "days_on_table",
    ],
    "investors": [
        "id", "name", "focus", "website", "email", "phone",
        "created_time", "days_on_table",
    ],
}

_INJECT = ("=", "+", "-", "@", "|", "\t", "\r")

def _safe(value: Any) -> str:
    if value is None: return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(_safe(v) for v in value)
    if isinstance(value, dict):
        return ""  # never emit nested payloads
    s = str(value)
    if s and s[0] in _INJECT:
        s = "'" + s
    return s

def build_csv(feed: str, rows: Iterable[Dict[str, Any]]) -> str:
    cols = FEED_WHITELIST.get(feed)
    if not cols:
        raise ValueError(f"no export whitelist for feed '{feed}'")
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    w.writerow(cols)
    for r in rows:
        w.writerow([_safe(r.get(c)) for c in cols])
    return buf.getvalue()

def filename_for(feed: str) -> str:
    d = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"bloodhound-{feed}-{d}.csv"
