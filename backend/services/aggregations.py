"""Shared aggregation and count definitions for the dashboard.

Previously `SampleOpportunityService` and `AirtableOpportunityService` each
carried their own copy of summary / pipeline / mission grouping. The copies had
drifted — one sorted on `o.get("priority_score", 0)` (which yields `None` when
the key exists but is unset, giving a different order and raising on mixed
types) while the other used `o.get("priority_score") or 0`, and only one
excluded closed statuses from the mission grouping. Both backends now call
these functions so a count means the same thing everywhere it is displayed.

Money rules:
- A monetary total is `None` when *no* contributing record carries a value.
  `None` means "unknown", `0` means "known to be zero". The UI must render
  those differently — a dash is honest, "$0" is a false statement about the
  pipeline.
- Every monetary total ships with the record counts behind it so the UI can
  qualify a partial sum.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from services.field_norm import coerce_number

CLOSED_STATUSES = ("Won", "Lost", "Disqualified")

PIPELINE_STATUSES = [
    "New",
    "Needs research",
    "Ready",
    "Conversation started",
    "Estimate requested",
    "Estimate sent",
    "Won",
    "Lost",
    "Disqualified",
]

ACTIONABLE_MISSIONS = [
    "Call Today",
    "Send Text",
    "Send Email",
    "Research First",
    "Visit Property",
    "Prepare Estimate",
    "Ask for Referral",
    "Follow Up",
    "Wait",
]

# Missions that mean "do something with a human today".
IMMEDIATE_MISSIONS = ("Call Today", "Send Text", "Visit Property")

# Published alongside the numbers so the dashboard can explain what it counted
# and so the definitions live in one auditable place.
COUNT_DEFINITIONS: Dict[str, str] = {
    "scope": ("All counts exclude non-canonical duplicates. Counts labelled "
              "'active' additionally exclude Won / Lost / Disqualified."),
    "new_opportunities": "Active records whose status is New.",
    "immediate_action": f"Active records whose mission is one of {', '.join(IMMEDIATE_MISSIONS)}.",
    "ready_to_contact": "Active records whose status is Ready.",
    "needs_research": "Active records with status 'Needs research' or mission 'Research First'.",
    "overlap": ("immediate_action, ready_to_contact and needs_research are "
                "attention lenses over the same active set, not a partition — "
                "a record can appear in more than one and they will not sum to "
                "active_count."),
    "total_pipeline_value": ("Sum of estimated value across active records. null when no "
                             "active record carries an estimate."),
    "missions_total": "Active records assigned to any mission bucket, including Wait.",
}


def is_canonical(record: Dict[str, Any]) -> bool:
    """Records are canonical unless the dedupe layer marked them otherwise.

    Defaults to True so a backend that has not run dedupe still aggregates.
    """
    return record.get("is_canonical", True) is not False


def canonical_only(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in records if is_canonical(r)]


def is_active(record: Dict[str, Any]) -> bool:
    return record.get("status") not in CLOSED_STATUSES


def score_of(record: Dict[str, Any]) -> float:
    """Sort key that tolerates missing, null, and string scores."""
    return coerce_number(record.get("priority_score")) or 0.0


def sort_by_score(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Descending score with a stable id tiebreak so equal scores do not
    reshuffle between requests."""
    return sorted(records, key=lambda r: (-score_of(r), str(r.get("id") or "")))


def money_total(records: Sequence[Dict[str, Any]],
                key: str = "estimated_value") -> Dict[str, Any]:
    """Sum a monetary column, preserving the unknown/zero distinction."""
    values = [coerce_number(r.get(key)) for r in records]
    known = [v for v in values if v is not None]
    total = sum(known) if known else None
    if total is not None and float(total).is_integer():
        total = int(total)
    return {
        "total": total,
        "records_with_value": len(known),
        "records_missing_value": len(values) - len(known),
        "records_considered": len(values),
    }


def summary(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    all_records = list(records)
    canonical = canonical_only(all_records)
    active = [r for r in canonical if is_active(r)]

    immediate = [r for r in active if r.get("daily_mission") in IMMEDIATE_MISSIONS]
    ready = [r for r in active if r.get("status") == "Ready"]
    needs_research = [r for r in active
                      if r.get("status") == "Needs research"
                      or r.get("daily_mission") == "Research First"]
    new_records = [r for r in active if r.get("status") == "New"]
    pipeline = money_total(active)

    return {
        "new_opportunities": len(new_records),
        "immediate_action": len(immediate),
        "ready_to_contact": len(ready),
        "needs_research": len(needs_research),
        "total_pipeline_value": pipeline["total"],
        "pipeline_value_coverage": {
            "records_with_value": pipeline["records_with_value"],
            "records_missing_value": pipeline["records_missing_value"],
            "records_considered": pipeline["records_considered"],
        },
        "active_count": len(active),
        "missions_total": len([r for r in active
                               if r.get("daily_mission") in ACTIONABLE_MISSIONS]),
        "canonical_count": len(canonical),
        "duplicates_suppressed": len(all_records) - len(canonical),
        "total_count": len(all_records),
        "definitions": COUNT_DEFINITIONS,
    }


def group_by_mission(records: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {m: [] for m in ACTIONABLE_MISSIONS}
    for record in canonical_only(records):
        if not is_active(record):
            continue
        mission = record.get("daily_mission")
        if mission in groups:
            groups[mission].append(record)
    return {mission: sort_by_score(items) for mission, items in groups.items()}


def pipeline_counts(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_status: Dict[str, List[Dict[str, Any]]] = {s: [] for s in PIPELINE_STATUSES}
    for record in canonical_only(records):
        status = record.get("status")
        if status in by_status:
            by_status[status].append(record)
    stages = []
    for status in PIPELINE_STATUSES:
        bucket = by_status[status]
        totals = money_total(bucket)
        stages.append({
            "status": status,
            "count": len(bucket),
            "value": totals["total"],
            "records_missing_value": totals["records_missing_value"],
        })
    return stages


def top(records: Iterable[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
    active = [r for r in canonical_only(records) if is_active(r)]
    return sort_by_score(active)[:limit]


def recent(records: Iterable[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
    items = canonical_only(records)
    items.sort(key=lambda r: (str(r.get("created_time") or ""), str(r.get("id") or "")),
               reverse=True)
    return items[:limit]


SEARCH_KEYS = ("name", "opportunity_id", "project_address", "decision_maker",
               "permit_number", "project_type")


def filter_records(
    records: Iterable[Dict[str, Any]],
    source: Optional[str] = None,
    status: Optional[str] = None,
    priority_band: Optional[str] = None,
    daily_mission: Optional[str] = None,
    project_type: Optional[str] = None,
    min_score: Optional[float] = None,
    q: Optional[str] = None,
    include_duplicates: bool = False,
) -> List[Dict[str, Any]]:
    """Shared list filtering. Duplicates are hidden unless explicitly requested
    so a suppressed record cannot be actioned from a list view."""
    results = list(records) if include_duplicates else canonical_only(records)

    predicates: List[Callable[[Dict[str, Any]], bool]] = []
    if source:
        predicates.append(lambda r: r.get("source") == source)
    if status:
        predicates.append(lambda r: r.get("status") == status)
    if priority_band:
        predicates.append(lambda r: r.get("priority_band") == priority_band)
    if daily_mission:
        predicates.append(lambda r: r.get("daily_mission") == daily_mission)
    if project_type:
        predicates.append(lambda r: r.get("project_type") == project_type)
    if min_score is not None:
        threshold = float(min_score)
        predicates.append(lambda r: score_of(r) >= threshold)
    if q:
        needle = q.lower()

        def matches(record: Dict[str, Any]) -> bool:
            blob = " ".join(str(record.get(k) or "") for k in SEARCH_KEYS).lower()
            return needle in blob

        predicates.append(matches)

    for predicate in predicates:
        results = [r for r in results if predicate(r)]
    return sort_by_score(results)
