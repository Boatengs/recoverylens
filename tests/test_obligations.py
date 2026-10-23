from __future__ import annotations

import pandas as pd

from recoverylens.fema import prepare_pa_projects
from recoverylens.obligations import DAMAGE_CATEGORY_LABELS, analyze_obligation_metrics


def project_record(
    project_id: int,
    *,
    category: str | None = "A",
    declaration: str | None = "2020-01-01T00:00:00Z",
    first: str | None = "2020-01-11T00:00:00Z",
    last: str | None = "2020-01-21T00:00:00Z",
    obligated: float = 100.0,
) -> dict[str, object]:
    return {
        "disasterNumber": 4496,
        "stateAbbreviation": "MA",
        "county": "Suffolk County",
        "stateNumberCode": "25",
        "countyCode": "025",
        "damageCategoryCode": category,
        "projectStatus": "Eligible",
        "gmProjectId": project_id,
        "projectAmount": obligated,
        "federalShareObligated": obligated,
        "totalObligated": obligated,
        "declarationDate": declaration,
        "firstObligationDate": first,
        "lastObligationDate": last,
    }


def test_obligation_metrics_map_categories_and_preserve_exceptions():
    prepared = prepare_pa_projects(
        [
            project_record(
                5, category="B", first="2020-01-10T00:00:00Z", last="2020-01-05T00:00:00Z"
            ),
            project_record(1),
            project_record(
                2, category="z", first="2020-01-06T00:00:00Z", last="2020-01-11T00:00:00Z"
            ),
            project_record(
                3, category="X", first="2019-12-25T00:00:00Z", last="2019-12-30T00:00:00Z"
            ),
            project_record(4, category=None, first=None, last=None),
        ]
    )

    result = analyze_obligation_metrics(prepared)

    assert result.projects["gmProjectId"].tolist() == [1, 2, 3, 4, 5]
    assert result.projects["damage_category_status"].tolist() == [
        "mapped",
        "mapped",
        "unmapped",
        "missing",
        "mapped",
    ]
    assert result.projects.loc[1, "damage_category_label"] == "Management Costs"
    assert result.projects.loc[0, "days_to_first_obligation"] == 10.0
    assert result.projects.loc[0, "obligation_window_days"] == 10.0
    assert pd.isna(result.projects.loc[2, "days_to_first_obligation"])
    assert bool(result.projects.loc[2, "first_obligation_before_declaration"])
    assert bool(result.projects.loc[4, "last_obligation_before_first"])

    assert result.summary["project_count"] == 5
    assert result.summary["mapped_category_count"] == 3
    assert result.summary["category_coverage_rate"] == 0.6
    assert result.summary["missing_category_count"] == 1
    assert result.summary["unmapped_category_count"] == 1
    assert result.summary["invalid_chronology_record_count"] == 2
    assert result.summary["publication_status"] == "warning"
    assert result.summary["warning_flags"] == [
        "missing_damage_categories",
        "unmapped_damage_categories",
        "missing_first_obligation_dates",
        "missing_last_obligation_dates",
        "invalid_timing_chronology",
    ]

    categories = result.category_summary.set_index("damage_category_code")
    assert list(categories.index[: len(DAMAGE_CATEGORY_LABELS)]) == list(DAMAGE_CATEGORY_LABELS)
    assert categories.loc["A", "project_count"] == 1
    assert categories.loc["A", "net_total_obligated"] == 100.0
    assert categories.loc["A", "first_obligation_days_median"] == 10.0
    assert categories.loc["X", "damage_category_status"] == "unmapped"


def test_obligation_metrics_blocks_empty_or_unusable_timing():
    empty = analyze_obligation_metrics(prepare_pa_projects([]))
    assert empty.summary["publication_status"] == "blocked"
    assert empty.summary["warning_flags"] == ["no_curated_projects"]

    missing_timing = analyze_obligation_metrics(
        prepare_pa_projects([project_record(1, first=None, last=None)])
    )
    assert missing_timing.summary["publication_status"] == "blocked"
    assert "no_valid_first_obligation_timing" in missing_timing.summary["warning_flags"]
