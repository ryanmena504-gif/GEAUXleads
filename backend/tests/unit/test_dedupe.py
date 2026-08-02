import random

from services import dedupe


def _records():
    return [
        {"id": "rec1", "name": "Ashby Roof", "contact_phone": "504-231-8890",
         "address": "1428 Prytania St", "city": "New Orleans",
         "opportunity_type": "Roof", "contact_confidence": "High",
         "date_discovered": "2026-07-01"},
        # Same phone, different source row.
        {"id": "rec2", "name": "Prytania roof permit", "contact_phone": "(504) 231-8890",
         "date_discovered": "2026-07-04"},
        # Same address written differently.
        {"id": "rec3", "name": "1428 Prytania", "address": "1428 prytania street",
         "date_discovered": "2026-07-06"},
        # Unrelated.
        {"id": "rec9", "name": "Carrollton Sunroom", "contact_phone": "504-555-0173",
         "address": "820 Dublin St", "date_discovered": "2026-07-02"},
    ]


def test_shared_phone_and_address_merge_into_one_group():
    index = dedupe.build_groups(_records())
    group_ids = {r: index["by_record"][r]["duplicate_group_id"]
                 for r in ("rec1", "rec2", "rec3", "rec9")}
    assert group_ids["rec1"] == group_ids["rec2"] == group_ids["rec3"]
    assert group_ids["rec9"] != group_ids["rec1"]


def test_exactly_one_canonical_per_group():
    index = dedupe.build_groups(_records())
    members = [index["by_record"][r] for r in ("rec1", "rec2", "rec3")]
    assert sum(1 for m in members if m["is_canonical"]) == 1
    canonical = next(m for m in members if m["is_canonical"])
    assert canonical["duplicate_of"] is None
    assert all(m["duplicate_of"] == "rec1" for m in members if not m["is_canonical"])


def test_richest_record_wins_the_election():
    # rec1 carries phone + address + category + confidence, so it outranks the
    # thinner rows that merged into its group.
    index = dedupe.build_groups(_records())
    assert index["by_record"]["rec1"]["is_canonical"]


def test_grouping_is_independent_of_input_order():
    baseline = dedupe.build_groups(_records())["by_record"]
    for seed in range(5):
        shuffled = _records()
        random.Random(seed).shuffle(shuffled)
        assert dedupe.build_groups(shuffled)["by_record"] == baseline


def test_fingerprint_is_stable_and_value_derived():
    a = {"id": "x", "contact_phone": "504-231-8890"}
    b = {"id": "y", "contact_phone": "+1 (504) 231-8890"}
    assert dedupe.fingerprint(a) == dedupe.fingerprint(b)


def test_record_without_identity_has_no_fingerprint():
    assert dedupe.fingerprint({"id": "skeleton", "name": "TBD"}) is None


def test_placeholder_phone_does_not_create_identity():
    # 5555555555 fails NANP validation, so it must not merge two properties.
    left = {"id": "a", "contact_phone": "555-555-5555", "address": "1 A St"}
    right = {"id": "b", "contact_phone": "555-555-5555", "address": "2 B St"}
    index = dedupe.build_groups([left, right])
    assert (index["by_record"]["a"]["duplicate_group_id"]
            != index["by_record"]["b"]["duplicate_group_id"])


def test_name_alone_does_not_merge_without_a_city():
    left = {"id": "a", "name": "John Smith"}
    right = {"id": "b", "name": "John Smith"}
    index = dedupe.build_groups([left, right])
    assert (index["by_record"]["a"]["duplicate_group_id"]
            != index["by_record"]["b"]["duplicate_group_id"])


def test_matched_on_explains_the_merge():
    index = dedupe.build_groups(_records())
    group = index["groups"][index["by_record"]["rec1"]["duplicate_group_id"]]
    assert any(k.startswith("phone:") for k in group["matched_on"])


def test_annotate_writes_metadata_onto_the_records():
    records = _records()
    dedupe.annotate(records)
    by_id = {r["id"]: r for r in records}
    assert by_id["rec1"]["is_canonical"] is True
    assert by_id["rec2"]["duplicate_of"] == "rec1"


def test_report_counts_suppressed_records():
    report = dedupe.duplicate_report(dedupe.build_groups(_records()))
    assert report["total_records"] == 4
    assert report["duplicate_groups"] == 1
    assert report["suppressed_records"] == 2
    assert report["actionable_records"] == 2


def test_dedupe_does_not_mutate_source_values():
    records = _records()
    before = records[1]["contact_phone"]
    dedupe.build_groups(records)
    assert records[1]["contact_phone"] == before
