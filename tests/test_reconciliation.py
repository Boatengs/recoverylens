from __future__ import annotations

import pytest

from recoverylens.fema import prepare_pa_projects
from recoverylens.reconciliation import (
    ReconciliationTolerance,
    reconcile_pa_projects,
    reconcile_pa_totals,
)


def project_record(
    project_id: int,
    *,
    amount: float = 100.0,
    disaster_number: int = 4496,
    state: str = "MA",
) -> dict[str, object]:
    return {
        "disasterNumber": disaster_number,
        "stateAbbreviation": state,
        "county": "Suffolk County",
        "stateNumberCode": "25",
        "countyCode": "025",
        "damageCategoryCode": "B",
        "projectStatus": "Eligible",
        "gmProjectId": project_id,
        "projectAmount": amount,
        "federalShareObligated": amount * 0.9,
        "totalObligated": amount * 0.9,
        "firstObligationDate": "2020-04-01T00:00:00Z",
        "lastObligationDate": "2020-04-02T00:00:00Z",
    }


def test_reconciliation_matches_when_source_is_unchanged():
    prepared = prepare_pa_projects([project_record(1), project_record(2, amount=200)])

    result = reconcile_pa_projects(prepared)

    assert result.summary["source_record_count"] == 2
    assert result.summary["curated_record_count"] == 2
    assert result.summary["duplicate_key_count"] == 0
    assert result.disaster_totals["reconciliation_status"].tolist() == ["matched"]
    assert result.state_totals["totalObligated_variance"].tolist() == [0.0]


def test_exact_duplicates_are_collapsed_and_reported_as_variance():
    record = project_record(1)
    prepared = prepare_pa_projects([record, record.copy()])

    result = reconcile_pa_projects(prepared)

    assert len(result.curated_projects) == 1
    assert result.summary["duplicate_key_count"] == 1
    assert result.summary["conflicting_key_count"] == 0
    assert result.summary["dropped_exact_duplicate_record_count"] == 1
    assert not bool(result.duplicate_projects.loc[0, "is_conflicting"])
    assert result.state_totals.loc[0, "source_totalObligated"] == 180.0
    assert result.state_totals.loc[0, "curated_totalObligated"] == 90.0
    assert result.state_totals.loc[0, "reconciliation_status"] == "variance"


def test_conflicting_duplicate_keys_are_excluded_and_identified():
    prepared = prepare_pa_projects(
        [project_record(1, amount=100), project_record(1, amount=130)]
    )

    result = reconcile_pa_projects(prepared)

    assert result.curated_projects.empty
    assert result.summary["conflicting_key_count"] == 1
    assert result.summary["excluded_conflict_record_count"] == 2
    assert bool(result.duplicate_projects.loc[0, "is_conflicting"])
    assert "projectAmount" in result.duplicate_projects.loc[0, "conflicting_fields"]
    assert result.disaster_totals.loc[0, "curated_projectAmount"] == 0.0
    assert result.disaster_totals.loc[0, "reconciliation_status"] == "variance"


def test_reconciliation_applies_explicit_dollar_tolerance():
    source = prepare_pa_projects([project_record(1)])
    curated = source.copy()
    curated.loc[0, "totalObligated"] += 0.005

    within = reconcile_pa_totals(
        source,
        curated,
        ["stateAbbreviation"],
        tolerance=ReconciliationTolerance(absolute_dollars=0.01),
    )
    outside = reconcile_pa_totals(
        source,
        curated,
        ["stateAbbreviation"],
        tolerance=ReconciliationTolerance(absolute_dollars=0.001),
    )

    assert within.loc[0, "reconciliation_status"] == "matched"
    assert outside.loc[0, "reconciliation_status"] == "variance"


def test_reconciliation_tolerance_rejects_negative_values():
    with pytest.raises(ValueError):
        ReconciliationTolerance(absolute_dollars=-0.01)
    with pytest.raises(ValueError):
        ReconciliationTolerance(relative=-1e-9)
