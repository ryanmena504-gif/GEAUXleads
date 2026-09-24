"""Aggregation and count definitions.

Two properties matter here: a monetary total must never turn an unknown into
`$0`, and a suppressed duplicate must never be counted twice.
"""
from services import aggregations as agg


def _records():
    return [
        {"id": "a", "status": "New", "daily_mission": "Call Today",
         "priority_score": 91, "estimated_value": 120000, "created_time": "2026-07-05"},
        {"id": "b", "status": "Ready", "daily_mission": "Send Text",
         "priority_score": 80, "estimated_value": None, "created_time": "2026-07-04"},
        {"id": "c", "status": "Needs research", "daily_mission": "Research First",
         "priority_score": None, "estimated_value": 40000, "created_time": "2026-07-03"},
        {"id": "d", "status": "Won", "daily_mission": "Follow Up",
         "priority_score": 70, "estimated_value": 900000, "created_time": "2026-07-02"},
        {"id": "e", "status": "New", "daily_mission": "Call Today",
         "priority_score": 88, "estimated_value": 50000, "created_time": "2026-07-06",
         "is_canonical": False, "duplicate_of": "a"},
    ]


# ------------------------------------------------------------------ money
def test_total_is_none_when_no_record_carries_a_value():
    result = agg.money_total([{"estimated_value": None}, {"estimated_value": ""}])
    assert result["total"] is None
    assert result["records_with_value"] == 0
    assert result["records_missing_value"] == 2


def test_known_zero_is_not_collapsed_to_unknown():
    result = agg.money_total([{"estimated_value": 0}])
    assert result["total"] == 0
    assert result["records_with_value"] == 1


def test_partial_total_reports_its_own_coverage():
    result = agg.money_total([{"estimated_value": 1000}, {"estimated_value": None}])
    assert result["total"] == 1000
    assert result["records_with_value"] == 1
    assert result["records_missing_value"] == 1


def test_summary_pipeline_value_is_null_when_nothing_is_estimated():
    records = [{"id": "x", "status": "New", "estimated_value": None}]
    summary = agg.summary(records)
    assert summary["total_pipeline_value"] is None
    assert summary["pipeline_value_coverage"]["records_missing_value"] == 1


# ------------------------------------------------------------------ counts
def test_summary_excludes_duplicates_and_closed_records():
    summary = agg.summary(_records())
    assert summary["total_count"] == 5
    assert summary["canonical_count"] == 4
    assert summary["duplicates_suppressed"] == 1
    assert summary["active_count"] == 3          # a, b, c — d is Won, e suppressed
    assert summary["total_pipeline_value"] == 160000


def test_summary_lenses_are_documented_as_overlapping():
    summary = agg.summary(_records())
    assert "not a partition" in summary["definitions"]["overlap"]
    assert summary["needs_research"] == 1
    assert summary["immediate_action"] == 2      # a: Call Today, b: Send Text
    assert summary["ready_to_contact"] == 1      # b again — the lenses overlap


def test_mission_grouping_drops_closed_and_duplicate_records():
    groups = agg.group_by_mission(_records())
    assert [r["id"] for r in groups["Call Today"]] == ["a"]
    assert groups["Follow Up"] == []             # Won
    assert set(groups) == set(agg.ACTIONABLE_MISSIONS)


def test_pipeline_counts_cover_every_stage_and_flag_partial_totals():
    stages = {s["status"]: s for s in agg.pipeline_counts(_records())}
    assert list(stages) == agg.PIPELINE_STATUSES
    assert stages["New"]["count"] == 1           # duplicate excluded
    assert stages["Ready"]["value"] is None
    assert stages["Ready"]["records_missing_value"] == 1
    assert stages["Estimate sent"]["count"] == 0
    assert stages["Estimate sent"]["value"] is None


# ------------------------------------------------------------------ sorting
def test_null_score_sorts_last_without_raising():
    ordered = [r["id"] for r in agg.sort_by_score(_records())]
    assert ordered[0] == "a"
    assert ordered[-1] == "c"                    # priority_score is None


def test_equal_scores_keep_a_stable_order():
    tied = [{"id": "z", "priority_score": 50}, {"id": "a", "priority_score": 50}]
    assert [r["id"] for r in agg.sort_by_score(tied)] == ["a", "z"]
    assert [r["id"] for r in agg.sort_by_score(list(reversed(tied)))] == ["a", "z"]


# ----------------------------------------------------------------- filtering
def test_list_hides_suppressed_duplicates_by_default():
    assert [r["id"] for r in agg.filter_records(_records(), status="New")] == ["a"]
    assert {r["id"] for r in agg.filter_records(_records(), status="New",
                                                include_duplicates=True)} == {"a", "e"}


def test_top_and_recent_exclude_duplicates():
    assert "e" not in {r["id"] for r in agg.top(_records())}
    assert "e" not in {r["id"] for r in agg.recent(_records())}


def test_top_excludes_closed_records():
    assert "d" not in {r["id"] for r in agg.top(_records())}


def test_records_without_dedupe_metadata_still_aggregate():
    """A backend that has not run dedupe must not silently count zero records."""
    plain = [{"id": "p", "status": "New", "estimated_value": 10}]
    assert agg.summary(plain)["canonical_count"] == 1
