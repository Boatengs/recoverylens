"""Deterministic machine- and human-readable Public Assistance quality reports."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .coverage import CountyCoverageResult
from .fema import DATASETS, OPEN_FEMA_BASE, Query
from .obligations import ObligationMetricsResult
from .reconciliation import MONEY_COLUMNS, PAReconciliationResult

REPORT_VERSION = "1.1"
LEVEL_DEFINITIONS = {
    "none": "The check passed and needs no quality warning.",
    "warning": "Review before publication; outputs remain available with caveats.",
    "error": "Blocking condition; do not publish analytical results from this run.",
}


@dataclass(frozen=True)
class PAQualityReport:
    """A quality report with deterministic JSON and Markdown renderings."""

    data: dict[str, object]
    markdown: str

    def json_text(self) -> str:
        """Return stable, standards-compliant JSON with a final newline."""

        return (
            json.dumps(
                self.data,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )


def _rate(numerator: int | float, denominator: int | float) -> float | None:
    if denominator == 0:
        return None
    return round(float(numerator) / float(denominator), 6)


def _optional_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), 6)


def _null_metrics(frame: pd.DataFrame) -> dict[str, dict[str, int | float | None]]:
    row_count = len(frame)
    return {
        str(column): {
            "null_count": int(frame[column].isna().sum()),
            "null_rate": _rate(int(frame[column].isna().sum()), row_count),
        }
        for column in frame.columns
    }


def _schema(frame: pd.DataFrame) -> list[dict[str, str]]:
    return [{"field": str(column), "dtype": str(frame[column].dtype)} for column in frame.columns]


def _financial_coverage(
    frame: pd.DataFrame,
) -> dict[str, dict[str, int | float | None]]:
    row_count = len(frame)
    return {
        field: {
            "non_null_count": int(frame[field].notna().sum()),
            "null_count": int(frame[field].isna().sum()),
            "coverage_rate": _rate(int(frame[field].notna().sum()), row_count),
        }
        for field in MONEY_COLUMNS
    }


def _check(
    check_id: str,
    *,
    severity: str,
    message: str,
) -> dict[str, str]:
    status = {"none": "passed", "warning": "warning", "error": "failed"}[severity]
    return {
        "check_id": check_id,
        "status": status,
        "severity": severity,
        "message": message,
    }


def _validation_checks(
    reconciliation: PAReconciliationResult,
    coverage: CountyCoverageResult,
    financial_coverage: Mapping[str, Mapping[str, Mapping[str, object]]],
    obligations: ObligationMetricsResult | None,
) -> list[dict[str, str]]:
    summary = reconciliation.summary
    source_count = int(summary["source_record_count"])
    curated_count = int(summary["curated_record_count"])
    exact_duplicates = int(summary["dropped_exact_duplicate_record_count"])
    conflicting_keys = int(summary["conflicting_key_count"])
    missing_project_ids = int(summary["missing_project_id_record_count"])
    variance_count = int(summary["disaster_variance_count"]) + int(summary["state_variance_count"])

    checks = [
        _check(
            "source_records_present",
            severity="none" if source_count else "error",
            message=(
                f"Retrieved {source_count:,} source records."
                if source_count
                else "No source records were retrieved."
            ),
        ),
        _check(
            "curated_records_present",
            severity="none" if curated_count else "error",
            message=(
                f"Produced {curated_count:,} curated records."
                if curated_count
                else "No curated records were produced."
            ),
        ),
        _check(
            "exact_duplicate_records",
            severity="warning" if exact_duplicates else "none",
            message=(
                f"Collapsed {exact_duplicates:,} exact duplicate records."
                if exact_duplicates
                else "No exact duplicate records were collapsed."
            ),
        ),
        _check(
            "conflicting_duplicate_keys",
            severity="error" if conflicting_keys else "none",
            message=(
                f"Found {conflicting_keys:,} conflicting project keys; "
                "affected records were excluded."
                if conflicting_keys
                else "No conflicting project keys were found."
            ),
        ),
        _check(
            "project_identifiers_complete",
            severity="warning" if missing_project_ids else "none",
            message=(
                f"Found {missing_project_ids:,} source records without a project identifier."
                if missing_project_ids
                else "All source records contain a project identifier."
            ),
        ),
        _check(
            "reconciliation_variances",
            severity="warning" if variance_count else "none",
            message=(
                f"Found {variance_count:,} disaster- or state-level reconciliation variances."
                if variance_count
                else "All disaster- and state-level reconciliations matched."
            ),
        ),
    ]

    curated_financial = financial_coverage["curated"]
    missing_financial = sum(int(metrics["null_count"]) for metrics in curated_financial.values())
    if not curated_count:
        financial_severity = "error"
        financial_message = (
            "Financial-field coverage is undefined because no curated records exist."
        )
    elif missing_financial:
        financial_severity = "warning"
        financial_message = f"Curated financial fields contain {missing_financial:,} null values."
    else:
        financial_severity = "none"
        financial_message = "All curated financial fields are populated."
    checks.append(
        _check(
            "financial_fields_complete",
            severity=financial_severity,
            message=financial_message,
        )
    )

    publication_status = str(coverage.summary["publication_status"])
    coverage_severity = {
        "ready": "none",
        "warning": "warning",
        "blocked": "error",
    }.get(publication_status, "error")
    warning_flags = [str(flag) for flag in coverage.summary["warning_flags"]]
    checks.append(
        _check(
            "county_attribution_coverage",
            severity=coverage_severity,
            message=(
                "County attribution meets publication thresholds."
                if not warning_flags
                else "County attribution flags: " + ", ".join(warning_flags) + "."
            ),
        )
    )
    if obligations is not None:
        obligation_summary = obligations.summary
        obligation_project_count = int(obligation_summary["project_count"])
        category_exceptions = int(obligation_summary["missing_category_count"]) + int(
            obligation_summary["unmapped_category_count"]
        )
        if not obligation_project_count:
            category_severity = "error"
            category_message = "Damage-category coverage is undefined because no projects exist."
        elif category_exceptions:
            category_severity = "warning"
            category_message = (
                f"Found {category_exceptions:,} projects with missing or unmapped categories."
            )
        else:
            category_severity = "none"
            category_message = "All project damage categories map to documented FEMA categories."
        checks.append(
            _check(
                "damage_category_coverage",
                severity=category_severity,
                message=category_message,
            )
        )
        category_flags = {"missing_damage_categories", "unmapped_damage_categories"}
        timing_flags = [
            str(flag)
            for flag in obligation_summary["warning_flags"]
            if str(flag) not in category_flags
        ]
        blocking_timing_flags = {"no_curated_projects", "no_valid_first_obligation_timing"}
        if blocking_timing_flags.intersection(timing_flags):
            timing_severity = "error"
        elif timing_flags:
            timing_severity = "warning"
        else:
            timing_severity = "none"
        checks.append(
            _check(
                "obligation_timing_coverage",
                severity=timing_severity,
                message=(
                    "Obligation timing fields are complete and chronologically valid."
                    if not timing_flags
                    else "Obligation timing flags: " + ", ".join(timing_flags) + "."
                ),
            )
        )
    return checks


def _source_frame(
    records: Sequence[Mapping[str, Any]],
    selected_fields: Sequence[str] | None,
) -> pd.DataFrame:
    frame = pd.DataFrame.from_records(records)
    if selected_fields is None:
        return frame.reindex(sorted(frame.columns), axis=1)
    for field in selected_fields:
        if field not in frame:
            frame[field] = pd.NA
    return frame[list(selected_fields)]


def build_pa_quality_report(
    records: Sequence[Mapping[str, Any]],
    reconciliation: PAReconciliationResult,
    coverage: CountyCoverageResult,
    *,
    query: Query,
    retrieved_at: str,
    filters: Mapping[str, object],
    obligations: ObligationMetricsResult | None = None,
) -> PAQualityReport:
    """Build one complete PA quality report from an executed pipeline run."""

    if query.dataset != "pa_projects":
        raise ValueError("PA quality reports require the pa_projects dataset")
    if not retrieved_at.strip():
        raise ValueError("retrieved_at must be a nonempty timestamp")

    source = _source_frame(records, query.select)
    curated = reconciliation.curated_projects
    financial_coverage = {
        "source": _financial_coverage(source),
        "curated": _financial_coverage(curated),
    }
    checks = _validation_checks(
        reconciliation,
        coverage,
        financial_coverage,
        obligations,
    )
    if any(check["severity"] == "error" for check in checks):
        validation_status = "failed"
        highest_severity = "error"
    elif any(check["severity"] == "warning" for check in checks):
        validation_status = "warning"
        highest_severity = "warning"
    else:
        validation_status = "passed"
        highest_severity = "none"

    status_breakdown = []
    for row in coverage.coverage_by_status.to_dict(orient="records"):
        status_breakdown.append(
            {
                "status": str(row["county_attribution_status"]),
                "record_count": int(row["record_count"]),
                "record_share": _optional_float(row["record_share"]),
                "known_obligation_record_count": int(row["known_obligation_record_count"]),
                "missing_obligation_record_count": int(row["missing_obligation_record_count"]),
                "net_obligated_dollars": _optional_float(row["total_obligated"]),
                "absolute_obligated_dollars": _optional_float(row["absolute_obligated"]),
                "absolute_obligation_share": _optional_float(row["absolute_obligation_share"]),
            }
        )

    reconciliation_summary = reconciliation.summary
    coverage_summary = coverage.summary
    report: dict[str, object] = {
        "report_version": REPORT_VERSION,
        "source": {
            "publisher": "Federal Emergency Management Agency",
            "dataset": DATASETS[query.dataset],
            "api_version": "v2",
            "url": f"{OPEN_FEMA_BASE}/{DATASETS[query.dataset]}",
            "retrieved_at": retrieved_at,
            "request": {
                "filter_expression": query.filter_expression,
                "filters": dict(sorted(filters.items())),
                "record_limit": query.max_records,
                "page_size": query.page_size,
                "order_by": query.order_by,
                "selected_fields": list(query.select or ()),
            },
        },
        "configuration": {
            "reconciliation": {
                "absolute_tolerance_dollars": _optional_float(
                    reconciliation_summary["absolute_tolerance_dollars"]
                ),
                "relative_tolerance": _optional_float(reconciliation_summary["relative_tolerance"]),
            },
            "county_coverage": {
                "minimum_record_coverage": _optional_float(
                    coverage_summary["minimum_record_coverage"]
                ),
                "minimum_obligation_coverage": _optional_float(
                    coverage_summary["minimum_obligation_coverage"]
                ),
            },
        },
        "schema": {
            "source": _schema(source),
            "curated": _schema(curated),
        },
        "row_counts": {
            "source": int(reconciliation_summary["source_record_count"]),
            "curated": int(reconciliation_summary["curated_record_count"]),
            "source_unique_projects": int(reconciliation_summary["source_unique_project_count"]),
            "curated_unique_projects": int(reconciliation_summary["curated_unique_project_count"]),
            "duplicate_keys": int(reconciliation_summary["duplicate_key_count"]),
            "dropped_exact_duplicates": int(
                reconciliation_summary["dropped_exact_duplicate_record_count"]
            ),
            "conflicting_keys": int(reconciliation_summary["conflicting_key_count"]),
            "excluded_conflict_records": int(
                reconciliation_summary["excluded_conflict_record_count"]
            ),
            "missing_project_ids": int(reconciliation_summary["missing_project_id_record_count"]),
            "unmatched_county_records": int(coverage_summary["unattributed_record_count"]),
        },
        "null_rates": {
            "source": _null_metrics(source),
            "curated": _null_metrics(curated),
        },
        "financial_field_coverage": financial_coverage,
        "county_attribution": {
            "attributed_record_count": int(coverage_summary["attributed_record_count"]),
            "unattributed_record_count": int(coverage_summary["unattributed_record_count"]),
            "record_attribution_rate": _optional_float(coverage_summary["record_attribution_rate"]),
            "net_total_obligated_dollars": _optional_float(coverage_summary["total_obligated"]),
            "net_attributed_obligated_dollars": _optional_float(
                coverage_summary["attributed_total_obligated"]
            ),
            "net_unattributed_obligated_dollars": _optional_float(
                coverage_summary["unattributed_total_obligated"]
            ),
            "absolute_total_obligated_dollars": _optional_float(
                coverage_summary["absolute_total_obligated"]
            ),
            "absolute_attributed_obligated_dollars": _optional_float(
                coverage_summary["attributed_absolute_obligated"]
            ),
            "obligation_attribution_rate": _optional_float(
                coverage_summary["obligation_attribution_rate"]
            ),
            "minimum_record_coverage": _optional_float(coverage_summary["minimum_record_coverage"]),
            "minimum_obligation_coverage": _optional_float(
                coverage_summary["minimum_obligation_coverage"]
            ),
            "status_breakdown": status_breakdown,
        },
        "validation": {
            "status": validation_status,
            "highest_severity": highest_severity,
            "level_definitions": dict(LEVEL_DEFINITIONS),
            "checks": checks,
        },
    }
    if obligations is not None:
        report["obligation_metrics"] = dict(obligations.summary)
    return PAQualityReport(data=report, markdown=render_quality_markdown(report))


def _cell(value: object) -> str:
    if value is None or value == "":
        return "Not set"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _percent(value: object) -> str:
    if value is None:
        return "Not available"
    return f"{float(value):.2%}"


def _dollars(value: object) -> str:
    if value is None:
        return "Not available"
    return f"${float(value):,.2f}"


def _days(value: object) -> str:
    if value is None:
        return "Not available"
    return f"{float(value):,.1f} days"


def render_quality_markdown(report: Mapping[str, object]) -> str:
    """Render a quality-report mapping in a fixed, review-friendly order."""

    source = report["source"]
    request = source["request"]
    configuration = report["configuration"]
    row_counts = report["row_counts"]
    validation = report["validation"]
    county = report["county_attribution"]
    lines = [
        "# Public Assistance Data-Quality Report",
        "",
        f"**Validation status:** `{str(validation['status']).upper()}`  ",
        f"**Highest severity:** `{str(validation['highest_severity']).upper()}`",
        "",
        "## Run metadata",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Publisher | {_cell(source['publisher'])} |",
        f"| Dataset | {_cell(source['dataset'])} |",
        f"| Source URL | {_cell(source['url'])} |",
        f"| Retrieved at | {_cell(source['retrieved_at'])} |",
        f"| Filter expression | {_cell(request['filter_expression'])} |",
        f"| Record limit | {_cell(request['record_limit'])} |",
        f"| Page size | {_cell(request['page_size'])} |",
        f"| Order | {_cell(request['order_by'])} |",
        "",
        "### Filter parameters",
        "",
        "| Parameter | Value |",
        "|---|---|",
    ]
    lines.extend(
        f"| {_cell(name)} | {_cell(value)} |" for name, value in request["filters"].items()
    )
    lines.extend(
        [
            "",
            "### Validation configuration",
            "",
            "| Setting | Value |",
            "|---|---:|",
            "| Absolute reconciliation tolerance | "
            f"{_dollars(configuration['reconciliation']['absolute_tolerance_dollars'])} |",
            "| Relative reconciliation tolerance | "
            f"{_cell(configuration['reconciliation']['relative_tolerance'])} |",
            "| Minimum county record coverage | "
            f"{_percent(configuration['county_coverage']['minimum_record_coverage'])} |",
            "| Minimum county obligation coverage | "
            f"{_percent(configuration['county_coverage']['minimum_obligation_coverage'])} |",
        ]
    )
    lines.extend(
        [
            "",
            "## Validation checks",
            "",
            "| Check | Status | Severity | Detail |",
            "|---|---|---|---|",
        ]
    )
    lines.extend(
        "| {check_id} | {status} | {severity} | {message} |".format(
            **{key: _cell(value) for key, value in check.items()}
        )
        for check in validation["checks"]
    )
    lines.extend(
        [
            "",
            "## Row counts",
            "",
            "| Metric | Count |",
            "|---|---:|",
        ]
    )
    lines.extend(f"| {_cell(metric)} | {int(value):,} |" for metric, value in row_counts.items())
    lines.extend(
        [
            "",
            "## County attribution",
            "",
            f"- Record attribution: **{_percent(county['record_attribution_rate'])}**",
            "- Absolute-obligation attribution: "
            f"**{_percent(county['obligation_attribution_rate'])}**",
            "- Net attributed obligations: "
            f"**{_dollars(county['net_attributed_obligated_dollars'])}**",
            "- Net unattributed obligations: "
            f"**{_dollars(county['net_unattributed_obligated_dollars'])}**",
            "",
            "| Status | Records | Record share | Net obligations | Absolute-obligation share |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    lines.extend(
        "| {status} | {records:,} | {record_share} | {dollars} | {obligation_share} |".format(
            status=_cell(row["status"]),
            records=int(row["record_count"]),
            record_share=_percent(row["record_share"]),
            dollars=_dollars(row["net_obligated_dollars"]),
            obligation_share=_percent(row["absolute_obligation_share"]),
        )
        for row in county["status_breakdown"]
    )
    if "obligation_metrics" in report:
        obligations = report["obligation_metrics"]
        flags = obligations["warning_flags"]
        lines.extend(
            [
                "",
                "## Obligation categories and timing",
                "",
                f"- Category coverage: **{_percent(obligations['category_coverage_rate'])}**",
                "- Complete timing coverage: "
                f"**{_percent(obligations['complete_timing_rate'])}**",
                "- Median days to first obligation: "
                f"**{_days(obligations['first_obligation_days_median'])}**",
                "- Median days to last obligation: "
                f"**{_days(obligations['last_obligation_days_median'])}**",
                "- Median obligation window: "
                f"**{_days(obligations['obligation_window_days_median'])}**",
                "- Timing status: "
                f"**{str(obligations['publication_status']).upper()}**",
                "- Flags: " + (", ".join(str(flag) for flag in flags) if flags else "None"),
            ]
        )
    lines.extend(
        [
            "",
            "## Financial-field coverage",
            "",
            "| Stage | Field | Non-null | Null | Coverage |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for stage, fields in report["financial_field_coverage"].items():
        for field, metrics in fields.items():
            lines.append(
                f"| {_cell(stage)} | {_cell(field)} | "
                f"{int(metrics['non_null_count']):,} | {int(metrics['null_count']):,} | "
                f"{_percent(metrics['coverage_rate'])} |"
            )
    lines.extend(
        [
            "",
            "## Schema",
            "",
            "| Stage | Field | Data type |",
            "|---|---|---|",
        ]
    )
    for stage, fields in report["schema"].items():
        for field in fields:
            lines.append(f"| {_cell(stage)} | {_cell(field['field'])} | {_cell(field['dtype'])} |")
    lines.extend(
        [
            "",
            "## Null rates",
            "",
            "| Stage | Field | Null count | Null rate |",
            "|---|---|---:|---:|",
        ]
    )
    for stage, fields in report["null_rates"].items():
        for field, metrics in fields.items():
            lines.append(
                f"| {_cell(stage)} | {_cell(field)} | {int(metrics['null_count']):,} | "
                f"{_percent(metrics['null_rate'])} |"
            )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `PASSED` means no configured quality warning was triggered.",
            "- `WARNING` means the outputs remain inspectable but require documented "
            "review before publication.",
            "- `FAILED` means an error-level condition blocks publication; retain the "
            "report for diagnosis.",
            "- A warning or failure describes data fitness for this run, not agency "
            "performance or causation.",
            "",
        ]
    )
    return "\n".join(lines)


def write_quality_report(report: PAQualityReport, output_dir: Path) -> tuple[Path, Path]:
    """Write deterministic JSON and Markdown report files."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "quality_report.json"
    markdown_path = output_dir / "quality_report.md"
    json_path.write_text(report.json_text(), encoding="utf-8")
    markdown_path.write_text(report.markdown, encoding="utf-8")
    return json_path, markdown_path
