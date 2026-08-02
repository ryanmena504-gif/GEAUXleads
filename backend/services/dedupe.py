"""Deterministic duplicate detection and canonical-record selection.

The live base accumulates several rows for the same property or contact — the
Make scenario appends a new Lead per inbound signal, and the same permit
frequently arrives from more than one source. Approving two of them sends the
same homeowner two messages.

This module groups records into duplicate sets and elects exactly one canonical
record per set. It is **read-only**: nothing here writes to Airtable. Grouping
is recomputed from field values on every cache refresh, so resolving a duplicate
in Airtable (correcting a phone number, clearing an address) immediately changes
the grouping with no stored state to migrate.

Determinism matters — the same set of records must always produce the same
group ids and the same canonical election, regardless of dict ordering — so
every ranking comparison ends in a total order tiebreak on record id.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from services.field_norm import (
    clean_text,
    has_address,
    is_valid_phone,
    normalize_address,
    normalize_email,
    normalize_name,
    normalize_permit,
    phone_digits,
)
from services.outreach_policy import FIELD_ALIASES, readiness_score, resolve

# Identity keys in descending strength. A shared key of any kind merges two
# records into the same group.
_PHONE_KEYS = FIELD_ALIASES["phone"]
_EMAIL_KEYS = FIELD_ALIASES["email"]
_ADDRESS_KEYS = FIELD_ALIASES["address"]
_PERMIT_KEYS = ("permit_number",)
_NAME_KEYS = FIELD_ALIASES["display_name"]


def _first_raw(record: Dict[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, "", []):
            return value
    return None


def identity_keys(record: Dict[str, Any]) -> List[str]:
    """Namespaced identity keys for a record, sorted and deduplicated.

    Two records are duplicates when they share at least one key.
    """
    keys: set[str] = set()

    for candidate in _PHONE_KEYS:
        # Only a dialable number is identity. A placeholder like 555-555-5555
        # is shared by unrelated rows and would merge two real properties.
        raw = record.get(candidate)
        if is_valid_phone(raw):
            keys.add(f"phone:{phone_digits(raw)}")

    for candidate in _EMAIL_KEYS:
        email = normalize_email(record.get(candidate))
        if email:
            keys.add(f"email:{email}")

    permit = normalize_permit(_first_raw(record, _PERMIT_KEYS))
    if permit:
        keys.add(f"permit:{permit}")

    if has_address(record, _ADDRESS_KEYS):
        address = normalize_address(_first_raw(record, _ADDRESS_KEYS))
        if address:
            keys.add(f"address:{address}")

    # A name alone is weak evidence, so it only counts when scoped to a city and
    # specific enough to be unlikely to collide.
    name = normalize_name(_first_raw(record, _NAME_KEYS))
    city = normalize_name(record.get("city"))
    if name and city and (len(name.split()) >= 2 or len(name) >= 8):
        keys.add(f"name_city:{name}|{city}")

    return sorted(keys)


def fingerprint(record: Dict[str, Any]) -> Optional[str]:
    """Stable per-record identity hash. None when the record has no identity at
    all (a skeleton row), which is itself a useful signal."""
    keys = identity_keys(record)
    if not keys:
        return None
    digest = hashlib.sha1("|".join(keys).encode("utf-8")).hexdigest()
    return f"fp_{digest[:16]}"


def _group_id(keys: Sequence[str]) -> str:
    digest = hashlib.sha1("|".join(sorted(keys)).encode("utf-8")).hexdigest()
    return f"dg_{digest[:12]}"


class _UnionFind:
    def __init__(self) -> None:
        self._parent: Dict[str, str] = {}

    def add(self, item: str) -> None:
        self._parent.setdefault(item, item)

    def find(self, item: str) -> str:
        self.add(item)
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:  # path compression
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: str, b: str) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            # Union by id keeps the result independent of insertion order.
            low, high = sorted((root_a, root_b))
            self._parent[high] = low


def _canonical_rank(record: Dict[str, Any]) -> Tuple[float, str, str]:
    """Sort key electing the canonical record: richest first, then oldest, then
    lowest id. The id tiebreak makes the election total and reproducible."""
    score, _ = readiness_score(record)
    created = clean_text(record.get("date_discovered")
                         or record.get("created_time")) or "9999"
    return (-score, created, str(record.get("id") or ""))


def build_groups(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Group records by shared identity and elect a canonical member for each.

    Returns a lookup keyed by record id plus the group index, so callers can
    annotate a single record without re-scanning the whole table.
    """
    records = [r for r in records if r.get("id")]
    union = _UnionFind()
    keys_by_record: Dict[str, List[str]] = {}

    for record in records:
        record_id = str(record["id"])
        union.add(record_id)
        keys = identity_keys(record)
        keys_by_record[record_id] = keys
        for key in keys:
            union.union(record_id, f"key::{key}")

    members: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        members.setdefault(union.find(str(record["id"])), []).append(record)

    by_record: Dict[str, Dict[str, Any]] = {}
    groups: Dict[str, Dict[str, Any]] = {}

    for member_list in members.values():
        member_list.sort(key=_canonical_rank)
        canonical = member_list[0]
        canonical_id = str(canonical["id"])
        all_keys = sorted({k for m in member_list for k in keys_by_record[str(m["id"])]})
        group_id = _group_id(all_keys) if all_keys else f"dg_solo_{canonical_id}"
        shared = _shared_keys(member_list, keys_by_record) if len(member_list) > 1 else []

        groups[group_id] = {
            "group_id": group_id,
            "size": len(member_list),
            "canonical_id": canonical_id,
            "member_ids": [str(m["id"]) for m in member_list],
            "matched_on": shared,
        }
        for member in member_list:
            member_id = str(member["id"])
            by_record[member_id] = {
                "duplicate_group_id": group_id,
                "duplicate_group_size": len(member_list),
                "is_canonical": member_id == canonical_id,
                "duplicate_of": None if member_id == canonical_id else canonical_id,
                "identity_fingerprint": fingerprint(member),
                "duplicate_matched_on": shared,
            }

    return {"by_record": by_record, "groups": groups}


def _shared_keys(members: Sequence[Dict[str, Any]],
                 keys_by_record: Dict[str, List[str]]) -> List[str]:
    """Which identity keys actually caused the merge — shown to the operator so
    a duplicate suppression is explainable rather than magic."""
    counts: Dict[str, int] = {}
    for member in members:
        for key in keys_by_record[str(member["id"])]:
            counts[key] = counts.get(key, 0) + 1
    return sorted(k for k, c in counts.items() if c > 1)


def annotate(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Attach duplicate metadata onto each record in place and return the index."""
    index = build_groups(records)
    for record in records:
        meta = index["by_record"].get(str(record.get("id")))
        if meta:
            record.update(meta)
    return index


def duplicate_report(index: Dict[str, Any]) -> Dict[str, Any]:
    """Operator-facing summary of the duplicate landscape."""
    groups = [g for g in index["groups"].values() if g["size"] > 1]
    groups.sort(key=lambda g: (-g["size"], g["group_id"]))
    suppressed = sum(g["size"] - 1 for g in groups)
    total = sum(g["size"] for g in index["groups"].values())
    no_identity = sum(
        1 for meta in index["by_record"].values()
        if meta["identity_fingerprint"] is None
    )
    return {
        "total_records": total,
        "duplicate_groups": len(groups),
        "suppressed_records": suppressed,
        "actionable_records": total - suppressed,
        "records_without_identity": no_identity,
        "groups": groups[:100],
    }
