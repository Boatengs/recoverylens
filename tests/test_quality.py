from __future__ import annotations

import json

from recoverylens.coverage import assess_county_coverage
from recoverylens.fema import Query, prepare_pa_projects
from recoverylens.obligations import analyze_obligation_metrics
from recoverylens.quality import build_pa_quality_report, write_quality_report
from recoverylens.reconciliation import reconcile_pa_projects


def project_record(
    project_id: int,
    *,
    county: str = "Suffolk County",
    county_code: str = "025",
    project_amount: float | None = 100.0,
    category: str | None = "B",
) -> dict[str, object]:
    return {
        "disasterNumber": 4496,
        "stateAbbreviation": "MA",
        "county": county,
        "stateNumberCode": "25",
        "countyCode": county_code,
        "damageCategoryCode": category,
        "projectStatus": "Eligible",
        "gmProjectId": project_id,
        "projectAmount": project_amount,
        "federalShareObligated": 90.0,
        "totalObligated": 90.0,
        "declarationDate": "2020-03-13T00:00:00Z",
        "firstObligationDate": "2020-04-01T00:00:00Z",
        "lastObligationDate": "2020-04-02T00:00:00Z",
    }


def build_report(records: list[dict[str, object]]):
    query = Query(
        dataset="pa_projects",
        filter_expression="stateAbbreviation eq 'MA' and declarationDate ge '2020-01-01'",
        select=tuple(records[0])
        if records
        else (
            "disasterNumber",
            "stateAbbreviation",
            "county",
            "stateNumberCode",
            "countyCode",
            "damageCategoryCode",
            "projectStatus",
            "gmProjectId",
            "projectAmount",
            "federalShareObligated",
            "totalObligated",
            "declarationDate",
            "firstObligationDate",
            "lastObligationDate",
        ),
        order_by="disasterNumber asc",
        max_records=500,
    )
    prepared = prepare_pa_projects(records)
    reconciliation = reconcile_pa_projects(prepared)
    coverage = assess_county_coverage(reconciliation.curated_projects)
    obligations = analyze_obligation_metrics(reconciliation.curated_projects)
    return build_pa_quality_report(
        records,
        reconciliation,
        coverage,
        query=query,
        retrieved_at="2026-10-23T00:00:00Z",
        filters={"state": "MA", "start_year": 2020, "disaster_number": None},
        obligations=obligations,
    )


def test_quality_report_has_stable_structure_and_metrics(tmp_path):
    first = project_record(1)
    records = [
        first,
        first.copy(),
        project_record(2, county="Statewide", project_amount=None),
    ]

    report = build_report(records)

    assert report.data["report_version"] == "1.1"
    assert report.data["source"]["retrieved_at"] == "2026-10-23T00:00:00Z"
    assert report.data["source"]["request"]["record_limit"] == 500
    assert report.data["row_counts"]["source"] == 3
    assert report.data["row_counts"]["curated"] == 2
    assert report.data["row_counts"]["dropped_exact_duplicates"] == 1
    assert report.data["null_rates"]["source"]["projectAmount"] == {
        "null_count": 1,
        "null_rate": 0.333333,
    }
    assert report.data["county_attribution"]["record_attribution_rate"] == 0.5
    assert report.data["financial_field_coverage"]["curated"]["projectAmount"] == {
        "non_null_count": 1,
        "null_count": 1,
        "coverage_rate": 0.5,
    }
    assert report.data["validation"]["status"] == "warning"
    assert report.data["obligation_metrics"]["category_coverage_rate"] == 1.0
    assert report.data["obligation_metrics"]["complete_timing_rate"] == 1.0
    assert "## Obligation categories and timing" in report.markdown
    assert "## Null rates" in report.markdown

    json_path, markdown_path = write_quality_report(report, tmp_path)
    assert json_path.read_text(encoding="utf-8") == report.json_text()
    assert markdown_path.read_text(encoding="utf-8") == report.markdown
    assert json.loads(report.json_text()) == report.data
    assert report.json_text() == build_report(records).json_text()


def test_quality_report_fails_when_source_is_empty():
    report = build_report([])

    assert report.data["validation"]["status"] == "failed"
    assert report.data["validation"]["highest_severity"] == "error"
    checks = {check["check_id"]: check for check in report.data["validation"]["checks"]}
    assert checks["source_records_present"]["status"] == "failed"
    assert checks["county_attribution_coverage"]["severity"] == "error"
    assert report.data["null_rates"]["source"]["totalObligated"]["null_rate"] is None


def test_category_warning_does_not_create_a_timing_warning():
    report = build_report([project_record(1, category=None)])
    checks = {check["check_id"]: check for check in report.data["validation"]["checks"]}

    assert checks["damage_category_coverage"]["status"] == "warning"
    assert checks["obligation_timing_coverage"]["status"] == "passed"


def test_quality_report_passes_for_complete_attributed_records():
    report = build_report([project_record(project_id) for project_id in range(1, 21)])

    assert report.data["validation"]["status"] == "passed"
    assert report.data["validation"]["highest_severity"] == "none"
    assert all(check["status"] == "passed" for check in report.data["validation"]["checks"])
