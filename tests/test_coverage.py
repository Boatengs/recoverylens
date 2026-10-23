from __future__ import annotations

import pandas as pd
import pytest

from recoverylens.coverage import CoverageThresholds, assess_county_coverage
from recoverylens.fema import prepare_pa_projects


def project_record(
    project_id: int,
    *,
    county: str | None = "Suffolk County",
    state_code: str | None = "25",
    county_code: str | None = "025",
    obligated: float | None = 100.0,
) -> dict[str, object]:
    return {
        "disasterNumber": 4496,
        "stateAbbreviation": "MA",
        "county": county,
        "stateNumberCode": state_code,
        "countyCode": county_code,
        "damageCategoryCode": "B",
        "projectStatus": "Eligible",
        "gmProjectId": project_id,
        "projectAmount": obligated,
        "federalShareObligated": obligated,
        "totalObligated": obligated,
        "declarationDate": "2020-03-13T00:00:00Z",
        "firstObligationDate": "2020-04-01T00:00:00Z",
        "lastObligationDate": "2020-04-02T00:00:00Z",
    }


def test_prepare_projects_classifies_county_attribution_reasons():
    prepared = prepare_pa_projects(
        [
            project_record(1),
            project_record(2, county="Statewide", county_code="025"),
            project_record(3, county="Multiple Counties", county_code="025"),
            project_record(4, county_code=None),
            project_record(5, county_code="000"),
        ]
    )

    assert prepared["county_attribution_status"].tolist() == [
        "attributed",
        "statewide",
        "multi_county",
        "missing_code",
        "invalid_code",
    ]
    assert prepared["county_fips"].tolist()[0] == "25025"
    assert prepared["county_fips"].isna().tolist()[1:] == [True, True, True, True]


def test_coverage_reports_each_reason_and_absolute_dollar_share():
    prepared = prepare_pa_projects(
        [
            project_record(1, obligated=100),
            project_record(2, county="Statewide", obligated=50),
            project_record(3, county="Various Counties", obligated=25),
            project_record(4, county_code=None, obligated=15),
            project_record(5, county_code="000", obligated=-10),
        ]
    )

    result = assess_county_coverage(prepared)

    assert len(result.unmatched_projects) == 4
    assert result.summary["attributed_record_count"] == 1
    assert result.summary["unattributed_record_count"] == 4
    assert result.summary["record_attribution_rate"] == 0.2
    assert result.summary["obligation_attribution_rate"] == 0.5
    assert result.summary["unattributed_total_obligated"] == 80.0
    assert result.summary["publication_status"] == "warning"
    assert result.summary["warning_flags"] == [
        "record_coverage_below_threshold",
        "obligation_coverage_below_threshold",
    ]
    counts = result.coverage_by_status.set_index("county_attribution_status")[
        "record_count"
    ]
    assert counts.to_dict() == {
        "attributed": 1,
        "statewide": 1,
        "multi_county": 1,
        "missing_code": 1,
        "invalid_code": 1,
    }


def test_coverage_threshold_boundary_is_ready():
    records = [project_record(project_id) for project_id in range(1, 20)]
    records.append(project_record(20, county="Statewide"))
    prepared = prepare_pa_projects(records)

    result = assess_county_coverage(prepared)

    assert result.summary["record_attribution_rate"] == 0.95
    assert result.summary["obligation_attribution_rate"] == 0.95
    assert result.summary["publication_status"] == "ready"
    assert result.summary["warning_flags"] == []


def test_missing_obligations_warn_and_absent_denominator_blocks():
    prepared = prepare_pa_projects(
        [
            project_record(1, obligated=None),
            project_record(2, county_code="000", obligated=None),
        ]
    )

    result = assess_county_coverage(prepared)

    assert result.summary["obligation_attribution_rate"] is None
    assert result.summary["missing_obligation_record_count"] == 2
    assert result.summary["publication_status"] == "blocked"
    assert result.summary["warning_flags"] == [
        "record_coverage_below_threshold",
        "no_obligation_denominator",
        "missing_obligation_values",
    ]
    assert pd.isna(
        result.coverage_by_status.loc[
            result.coverage_by_status["county_attribution_status"].eq("attributed"),
            "total_obligated",
        ].iloc[0]
    )


def test_empty_source_blocks_publication_without_dividing_by_zero():
    result = assess_county_coverage(prepare_pa_projects([]))

    assert result.summary["record_attribution_rate"] is None
    assert result.summary["obligation_attribution_rate"] is None
    assert result.summary["publication_status"] == "blocked"
    assert result.summary["warning_flags"] == [
        "no_source_records",
        "no_obligation_denominator",
    ]
    assert result.unmatched_projects.empty


def test_coverage_thresholds_reject_out_of_range_values():
    with pytest.raises(ValueError):
        CoverageThresholds(minimum_record_coverage=1.01)
    with pytest.raises(ValueError):
        CoverageThresholds(minimum_obligation_coverage=-0.01)
