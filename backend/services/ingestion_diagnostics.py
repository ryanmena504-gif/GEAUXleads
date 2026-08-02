"""Ingestion validation, field-coverage diagnostics, and exception reporting.

The Make.com scenario writes into Airtable and this app reads what lands there.
When a mapping is wrong the failure is silent: the column exists, it is simply
never populated, and the dashboard renders "Not available yet" forever. This
module makes that visible — it reports which mapped columns are actually being
filled, which columns exist in Airtable that the app does not read, which
expected columns are missing entirely, and which individual records carry
values that cannot be interpreted.

Everything here is read-only and derived from the records already in cache, so
producing a report costs no extra Airtable calls.
"""
from __future__ import annotations

import threading
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from services.field_norm import (
    clean_text,
    coerce_number,
    has_address,
    is_blank,
    is_valid_email,
    is_valid_phone,
    normalize_email,
)

# Severity of a validation issue.
ERROR = "error"      # the value is present but unusable
WARN = "warning"     # the value is absent and outreach depends on it
INFO = "info"        # worth surfacing, not a problem on its own

# Internal keys checked for type/format correctness, grouped by validator.
_PHONE_FIELDS = ("contact_phone", "phone_number", "phone", "phone_alt")
_EMAIL_FIELDS = ("contact_email", "email", "email_alt")
_MONEY_FIELDS = ("estimated_job_value", "estimated_value", "closed_revenue",
                 "estimated_gross_profit", "construction_value")
_DATE_FIELDS = ("date_discovered", "created_time", "message_sent_date",
                "next_follow_up", "date_contacted", "date_replied",
                "validated_at", "message_generated_at", "permit_filing_date")

# Without these a record cannot become an outreach action, whatever else it has.
_OUTREACH_CRITICAL = ("contact", "address", "category")

MAX_SAMPLES = 5


def _parse_date(value: Any) -> bool:
    text = clean_text(value)
    if not text:
        return True  # absent is not invalid
    candidate = text.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(candidate)
        return True
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%b %d, %Y"):
        try:
            datetime.strptime(text, fmt)
            return True
        except ValueError:
            continue
    return False


def validate_record(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Field-level validation of one projected record.

    Reports values that are present but uninterpretable (an error the pipeline
    can fix) separately from values that are simply absent (a coverage gap).
    """
    issues: List[Dict[str, Any]] = []

    def add(code: str, severity: str, field: Optional[str], message: str) -> None:
        issues.append({"code": code, "severity": severity, "field": field,
                       "message": message, "record_id": record.get("id")})

    for key in _PHONE_FIELDS:
        value = record.get(key)
        if not is_blank(value) and not is_valid_phone(value):
            add("invalid_phone", ERROR, key,
                f"“{clean_text(value)}” is not a dialable 10-digit number.")

    for key in _EMAIL_FIELDS:
        value = record.get(key)
        if is_blank(value):
            continue
        if normalize_email(value) is None:
            add("invalid_email", ERROR, key,
                f"“{clean_text(value)}” does not contain a parsable email address.")
        elif not is_valid_email(value):
            add("placeholder_email", ERROR, key,
                f"“{clean_text(value)}” is a placeholder or no-reply address.")

    for key in _MONEY_FIELDS:
        value = record.get(key)
        if not is_blank(value) and coerce_number(value) is None:
            add("unparsable_money", ERROR, key,
                f"“{clean_text(value)}” cannot be read as a number.")

    for key in _DATE_FIELDS:
        value = record.get(key)
        if not is_blank(value) and not _parse_date(value):
            add("unparsable_date", ERROR, key,
                f"“{clean_text(value)}” is not a recognisable date.")

    has_contact = any(is_valid_phone(record.get(k)) for k in _PHONE_FIELDS) or \
        any(is_valid_email(record.get(k)) for k in _EMAIL_FIELDS)
    if not has_contact:
        add("missing_contact", WARN, "Contact phone / Contact email",
            "No verified phone or email — the record can never become outreach.")
    if not has_address(record, ("address", "project_address")):
        add("missing_address", WARN, "Address",
            "No street address — only a city, or nothing at all.")
    if is_blank(record.get("opportunity_type") or record.get("project_type")):
        add("missing_category", WARN, "Opportunity type",
            "No project or service category.")
    if is_blank(record.get("name")):
        add("missing_name", WARN, "Leads Name", "Record has no name.")

    return issues


def field_coverage(records: Sequence[Dict[str, Any]],
                   field_map: Dict[str, str]) -> List[Dict[str, Any]]:
    """Populated-row percentage for every mapped Airtable column.

    A mapped column at 0% is the signature of a Make-side mapping gap: the app
    reads it, Airtable has it, nothing ever writes it.
    """
    total = len(records) or 1
    coverage: List[Dict[str, Any]] = []
    for airtable_name, internal in sorted(field_map.items()):
        populated = sum(1 for r in records if not is_blank(r.get(internal)))
        coverage.append({
            "airtable_field": airtable_name,
            "internal_key": internal,
            "populated": populated,
            "total": len(records),
            "coverage_pct": round(100.0 * populated / total, 1),
            "status": ("never_populated" if populated == 0
                       else "sparse" if populated / total < 0.25
                       else "ok"),
        })
    return coverage


def mapping_gaps(schema_field_names: Iterable[str],
                 known_field_map: Dict[str, str],
                 active_field_map: Dict[str, str]) -> Dict[str, Any]:
    """Reconcile what the app expects against what the base actually has."""
    schema = set(schema_field_names)
    expected = set(known_field_map)
    active = set(active_field_map)
    return {
        # Expected by the app, absent from Airtable — the app renders these as
        # "Not available yet". Fixing means adding the column, or accepting the gap.
        "expected_but_absent": sorted(expected - schema),
        # Present in Airtable, not read by the app — potentially useful data the
        # dashboard is blind to.
        "present_but_unmapped": sorted(schema - expected),
        "mapped_and_present": sorted(active),
    }


def recommendations(coverage: Sequence[Dict[str, Any]],
                    gaps: Dict[str, Any],
                    issue_counts: Dict[str, int]) -> List[Dict[str, Any]]:
    """Concrete, actionable next steps — deliberately phrased as Make-side or
    Airtable-side configuration, since this app must not mutate either."""
    recs: List[Dict[str, Any]] = []

    never = [c["airtable_field"] for c in coverage if c["status"] == "never_populated"]
    if never:
        recs.append({
            "area": "make_scenario",
            "severity": "high",
            "title": f"{len(never)} mapped column(s) are never populated",
            "detail": ("These Airtable columns exist and the app reads them, but no "
                       "record has a value. Add the corresponding output mapping in "
                       "the Make scenario's Airtable 'Create/Update a Record' module."),
            "fields": never[:25],
        })

    sparse = [c["airtable_field"] for c in coverage if c["status"] == "sparse"]
    if sparse:
        recs.append({
            "area": "make_scenario",
            "severity": "medium",
            "title": f"{len(sparse)} column(s) populated on under a quarter of records",
            "detail": ("Likely a conditional branch in the scenario that only maps the "
                       "field on some paths, or an enrichment step that fails silently."),
            "fields": sparse[:25],
        })

    if gaps["expected_but_absent"]:
        recs.append({
            "area": "airtable_schema",
            "severity": "medium",
            "title": f"{len(gaps['expected_but_absent'])} expected column(s) missing from the base",
            "detail": ("The app degrades gracefully and shows 'Not available yet'. Add the "
                       "column in Airtable only if you want the data surfaced; no app "
                       "change is needed either way."),
            "fields": gaps["expected_but_absent"],
        })

    if gaps["present_but_unmapped"]:
        recs.append({
            "area": "app_field_map",
            "severity": "low",
            "title": f"{len(gaps['present_but_unmapped'])} Airtable column(s) not read by the app",
            "detail": ("Add an entry to LIVE_FIELDS in services/airtable_service.py (or "
                       "LEADS_FIELD_MAP in services/leads_service.py) to surface these."),
            "fields": gaps["present_but_unmapped"][:40],
        })

    if issue_counts.get("invalid_phone"):
        recs.append({
            "area": "make_scenario",
            "severity": "high",
            "title": f"{issue_counts['invalid_phone']} record(s) hold an unusable phone number",
            "detail": ("Normalize to 10-digit NANP before writing to Airtable — strip "
                       "extensions and country prefixes in the scenario rather than "
                       "storing raw scraped text."),
        })

    if issue_counts.get("invalid_email") or issue_counts.get("placeholder_email"):
        count = issue_counts.get("invalid_email", 0) + issue_counts.get("placeholder_email", 0)
        recs.append({
            "area": "make_scenario",
            "severity": "high",
            "title": f"{count} record(s) hold an unusable email address",
            "detail": ("Validate the enrichment output before mapping it; placeholder and "
                       "no-reply addresses should be written as blank, not stored."),
        })

    if issue_counts.get("unparsable_money"):
        recs.append({
            "area": "airtable_schema",
            "severity": "medium",
            "title": f"{issue_counts['unparsable_money']} record(s) hold a non-numeric money value",
            "detail": ("Retype the column as Currency/Number in Airtable, or strip "
                       "formatting in the scenario. Text money values are excluded from "
                       "pipeline totals."),
        })

    if issue_counts.get("unparsable_date"):
        recs.append({
            "area": "make_scenario",
            "severity": "medium",
            "title": f"{issue_counts['unparsable_date']} record(s) hold an unparsable date",
            "detail": "Emit ISO-8601 (YYYY-MM-DD) from the scenario before mapping to Airtable.",
        })

    return recs


class IngestionRecorder:
    """Collects per-refresh transform exceptions.

    A record that raises during projection is dropped from the cache rather than
    taking the whole refresh down; without this the loss is invisible.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: List[Dict[str, Any]] = []
        self._last_run: Optional[str] = None
        self._records_seen = 0
        self._records_projected = 0

    def start(self) -> None:
        with self._lock:
            self._failures = []
            self._records_seen = 0
            self._records_projected = 0

    def record_seen(self) -> None:
        with self._lock:
            self._records_seen += 1

    def record_projected(self) -> None:
        with self._lock:
            self._records_projected += 1

    def record_failure(self, record_id: Optional[str], error: BaseException) -> None:
        with self._lock:
            if len(self._failures) < 50:
                self._failures.append({
                    "record_id": record_id,
                    "error_type": type(error).__name__,
                    "error": str(error)[:300],
                    "at": datetime.now(timezone.utc).isoformat(),
                })

    def finish(self) -> None:
        with self._lock:
            self._last_run = datetime.now(timezone.utc).isoformat()

    def report(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "last_run": self._last_run,
                "records_seen": self._records_seen,
                "records_projected": self._records_projected,
                "records_dropped": self._records_seen - self._records_projected,
                "failures": list(self._failures),
            }


def build_report(records: Sequence[Dict[str, Any]],
                 field_map: Dict[str, str],
                 known_field_map: Dict[str, str],
                 schema_field_names: Iterable[str],
                 pipeline_report: Optional[Dict[str, Any]] = None,
                 duplicates: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Assemble the full ingestion diagnostic."""
    issues_by_record = {str(r.get("id")): validate_record(r) for r in records}
    all_issues = [issue for issues in issues_by_record.values() for issue in issues]

    counts = Counter(issue["code"] for issue in all_issues)
    by_severity = Counter(issue["severity"] for issue in all_issues)
    coverage = field_coverage(records, field_map)
    gaps = mapping_gaps(schema_field_names, known_field_map, field_map)

    samples: Dict[str, List[Dict[str, Any]]] = {}
    for issue in all_issues:
        bucket = samples.setdefault(issue["code"], [])
        if len(bucket) < MAX_SAMPLES:
            bucket.append({"record_id": issue["record_id"],
                           "field": issue["field"],
                           "message": issue["message"]})

    blocking_codes = {f"missing_{critical}" for critical in _OUTREACH_CRITICAL}
    outreach_ready = sum(
        1 for issues in issues_by_record.values()
        if not any(issue["code"] in blocking_codes for issue in issues)
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "records_analyzed": len(records),
        "issue_counts": dict(counts),
        "issues_by_severity": dict(by_severity),
        "issue_samples": samples,
        "field_coverage": coverage,
        "coverage_summary": {
            "mapped_fields": len(coverage),
            "never_populated": sum(1 for c in coverage if c["status"] == "never_populated"),
            "sparse": sum(1 for c in coverage if c["status"] == "sparse"),
            "ok": sum(1 for c in coverage if c["status"] == "ok"),
        },
        "mapping_gaps": gaps,
        "pipeline_exceptions": pipeline_report or {},
        "duplicates": duplicates or {},
        "outreach_ready_records": outreach_ready,
        "recommendations": recommendations(coverage, gaps, dict(counts)),
    }
