from services import ingestion_diagnostics as diag


def _codes(issues):
    return {i["code"] for i in issues}


def test_present_but_unusable_values_are_errors():
    issues = diag.validate_record({
        "id": "rec1",
        "contact_phone": "555-1234",
        "contact_email": "owner@example.com",
        "estimated_job_value": "about forty grand",
        "date_discovered": "last tuesday",
    })
    assert {"invalid_phone", "placeholder_email", "unparsable_money",
            "unparsable_date"} <= _codes(issues)
    assert all(i["severity"] == diag.ERROR
               for i in issues if i["code"].startswith(("invalid", "unparsable", "placeholder")))


def test_absent_values_are_warnings_not_errors():
    issues = diag.validate_record({"id": "rec2"})
    missing = [i for i in issues if i["code"].startswith("missing_")]
    assert {"missing_contact", "missing_address",
            "missing_category", "missing_name"} <= _codes(issues)
    assert all(i["severity"] == diag.WARN for i in missing)


def test_a_complete_record_raises_nothing():
    assert diag.validate_record({
        "id": "rec3",
        "name": "Ashby Roof",
        "contact_phone": "504-231-8890",
        "contact_email": "marie@ashbyhome.net",
        "address": "1428 Prytania St",
        "opportunity_type": "Roof",
        "estimated_job_value": 48000,
        "date_discovered": "2026-07-01",
    }) == []


def test_unparsable_email_is_distinguished_from_a_placeholder():
    assert "invalid_email" in _codes(diag.validate_record({"id": "r", "contact_email": "marie at home"}))
    assert "placeholder_email" in _codes(diag.validate_record({"id": "r", "contact_email": "a@example.com"}))


def test_iso_and_us_dates_both_parse():
    for value in ("2026-07-01", "2026-07-01T09:00:00Z", "07/01/2026", "Jul 01, 2026"):
        assert "unparsable_date" not in _codes(
            diag.validate_record({"id": "r", "date_discovered": value})), value


def test_coverage_flags_a_column_nothing_ever_writes():
    records = [{"id": "1", "name": "A", "permit_number": None},
               {"id": "2", "name": "B", "permit_number": None}]
    coverage = {c["airtable_field"]: c
                for c in diag.field_coverage(records, {"Leads Name": "name",
                                                       "Permit number": "permit_number"})}
    assert coverage["Permit number"]["status"] == "never_populated"
    assert coverage["Permit number"]["coverage_pct"] == 0.0
    assert coverage["Leads Name"]["status"] == "ok"


def test_coverage_flags_a_sparsely_written_column():
    records = [{"id": str(i), "city": "New Orleans" if i == 0 else None} for i in range(10)]
    coverage = diag.field_coverage(records, {"City": "city"})[0]
    assert coverage["status"] == "sparse"
    assert coverage["coverage_pct"] == 10.0


def test_mapping_gaps_reconcile_the_app_against_the_base():
    gaps = diag.mapping_gaps(
        schema_field_names=["Leads Name", "City", "Referred by"],
        known_field_map={"Leads Name": "name", "City": "city", "Permit number": "permit_number"},
        active_field_map={"Leads Name": "name", "City": "city"},
    )
    assert gaps["expected_but_absent"] == ["Permit number"]
    assert gaps["present_but_unmapped"] == ["Referred by"]


def test_recommendations_are_phrased_as_make_or_airtable_configuration():
    coverage = [{"airtable_field": "Contact email", "status": "never_populated"}]
    gaps = {"expected_but_absent": [], "present_but_unmapped": [], "mapped_and_present": []}
    recs = diag.recommendations(coverage, gaps, {"invalid_phone": 3})
    areas = {r["area"] for r in recs}
    assert areas <= {"make_scenario", "airtable_schema", "app_field_map"}
    assert any("Make scenario" in r["detail"] for r in recs)


def test_recorder_makes_dropped_records_visible():
    recorder = diag.IngestionRecorder()
    recorder.start()
    for _ in range(3):
        recorder.record_seen()
    recorder.record_projected()
    recorder.record_projected()
    recorder.record_failure("recBAD", ValueError("bad estimated value"))
    recorder.finish()

    report = recorder.report()
    assert report["records_seen"] == 3
    assert report["records_projected"] == 2
    assert report["records_dropped"] == 1
    assert report["failures"][0]["record_id"] == "recBAD"
    assert report["failures"][0]["error_type"] == "ValueError"
    assert report["last_run"] is not None


def test_recorder_start_clears_the_previous_run():
    recorder = diag.IngestionRecorder()
    recorder.start()
    recorder.record_seen()
    recorder.record_failure("recBAD", ValueError("x"))
    recorder.start()
    assert recorder.report()["failures"] == []
    assert recorder.report()["records_seen"] == 0


def test_full_report_counts_outreach_ready_records():
    records = [
        {"id": "good", "name": "A", "contact_phone": "504-231-8890",
         "address": "1428 Prytania St", "opportunity_type": "Roof"},
        {"id": "bad", "name": "B"},
    ]
    report = diag.build_report(
        records=records,
        field_map={"Leads Name": "name", "Contact phone": "contact_phone"},
        known_field_map={"Leads Name": "name", "Contact phone": "contact_phone",
                         "Permit number": "permit_number"},
        schema_field_names=["Leads Name", "Contact phone", "Referred by"],
        pipeline_report={"records_dropped": 0},
        duplicates={"duplicate_groups": 0},
    )
    assert report["records_analyzed"] == 2
    assert report["outreach_ready_records"] == 1
    assert report["issue_counts"]["missing_contact"] == 1
    assert report["mapping_gaps"]["expected_but_absent"] == ["Permit number"]
    assert report["coverage_summary"]["mapped_fields"] == 2
    assert report["recommendations"]


def test_report_caps_issue_samples():
    records = [{"id": f"r{i}", "name": "x", "contact_phone": "555-1234"} for i in range(20)]
    report = diag.build_report(records=records, field_map={"Leads Name": "name"},
                               known_field_map={"Leads Name": "name"},
                               schema_field_names=["Leads Name"])
    assert len(report["issue_samples"]["invalid_phone"]) == diag.MAX_SAMPLES
    assert report["issue_counts"]["invalid_phone"] == 20
