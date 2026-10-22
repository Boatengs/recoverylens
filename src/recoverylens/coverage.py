"""County-attribution coverage diagnostics for Public Assistance projects."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

ATTRIBUTION_STATUSES = (
    "attributed",
    "statewide",
    "multi_county",
    "missing_code",
    "invalid_code",
)


@dataclass(frozen=True)
class CoverageThresholds:
    """Minimum acceptable county-attribution shares for publication."""

    minimum_record_coverage: float = 0.95
    minimum_obligation_coverage: float = 0.95

    def __post_init__(self) -> None:
        for name, value in (
            ("minimum_record_coverage", self.minimum_record_coverage),
            ("minimum_obligation_coverage", self.minimum_obligation_coverage),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class CountyCoverageResult:
    """Auditable county-attribution outputs from one prepared project table."""

    coverage_by_status: pd.DataFrame
    unmatched_projects: pd.DataFrame
    summary: dict[str, object]


def _sum_or_none(values: pd.Series) -> float | None:
    value = values.sum(min_count=1)
    return None if pd.isna(value) else round(float(value), 2)


def _share(numerator: float | int, denominator: float | int) -> float | None:
    if denominator == 0:
        return None
    return round(float(numerator) / float(denominator), 6)


def assess_county_coverage(
    frame: pd.DataFrame,
    *,
    thresholds: CoverageThresholds | None = None,
) -> CountyCoverageResult:
    """Measure county attribution by records and absolute obligated dollars.

    Net obligated dollars remain visible in the output, while the coverage share
    uses absolute dollars so positive and negative adjustments cannot cancel out.
    """

    active_thresholds = thresholds or CoverageThresholds()
    required = {
        "county_attribution_status",
        "is_county_attributed",
        "totalObligated",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"County coverage data are missing required fields: {missing}")

    observed_statuses = [
        str(status)
        for status in frame["county_attribution_status"].dropna().unique()
        if str(status) not in ATTRIBUTION_STATUSES
    ]
    statuses = [*ATTRIBUTION_STATUSES, *sorted(observed_statuses)]
    total_records = len(frame)
    known_obligations = frame["totalObligated"].dropna()
    absolute_obligation_denominator = float(known_obligations.abs().sum())

    rows: list[dict[str, object]] = []
    for status in statuses:
        subset = frame.loc[frame["county_attribution_status"].eq(status)]
        obligations = subset["totalObligated"].dropna()
        absolute_obligated = float(obligations.abs().sum())
        rows.append(
            {
                "county_attribution_status": status,
                "record_count": len(subset),
                "record_share": _share(len(subset), total_records),
                "known_obligation_record_count": len(obligations),
                "missing_obligation_record_count": int(
                    subset["totalObligated"].isna().sum()
                ),
                "total_obligated": _sum_or_none(subset["totalObligated"])
                if len(subset)
                else 0.0,
                "absolute_obligated": round(absolute_obligated, 2),
                "absolute_obligation_share": _share(
                    absolute_obligated, absolute_obligation_denominator
                ),
            }
        )
    coverage_by_status = pd.DataFrame(rows)

    attributed = frame.loc[frame["is_county_attributed"]]
    unmatched = frame.loc[~frame["is_county_attributed"]].copy().reset_index(drop=True)
    attributed_obligations = attributed["totalObligated"].dropna()
    attributed_absolute_obligated = float(attributed_obligations.abs().sum())
    record_attribution_rate = _share(len(attributed), total_records)
    obligation_attribution_rate = _share(
        attributed_absolute_obligated, absolute_obligation_denominator
    )

    warning_flags: list[str] = []
    if total_records == 0:
        warning_flags.append("no_source_records")
    elif record_attribution_rate is not None and (
        record_attribution_rate < active_thresholds.minimum_record_coverage
    ):
        warning_flags.append("record_coverage_below_threshold")
    if absolute_obligation_denominator == 0:
        warning_flags.append("no_obligation_denominator")
    elif obligation_attribution_rate is not None and (
        obligation_attribution_rate < active_thresholds.minimum_obligation_coverage
    ):
        warning_flags.append("obligation_coverage_below_threshold")
    missing_obligation_count = int(frame["totalObligated"].isna().sum())
    if missing_obligation_count:
        warning_flags.append("missing_obligation_values")

    blocking_flags = {"no_source_records", "no_obligation_denominator"}
    if blocking_flags.intersection(warning_flags):
        publication_status = "blocked"
    elif warning_flags:
        publication_status = "warning"
    else:
        publication_status = "ready"

    total_obligated = _sum_or_none(frame["totalObligated"])
    attributed_total_obligated = _sum_or_none(attributed["totalObligated"])
    unmatched_total_obligated = _sum_or_none(unmatched["totalObligated"])
    summary: dict[str, object] = {
        "input_record_count": total_records,
        "attributed_record_count": len(attributed),
        "unattributed_record_count": len(unmatched),
        "record_attribution_rate": record_attribution_rate,
        "known_obligation_record_count": len(known_obligations),
        "missing_obligation_record_count": missing_obligation_count,
        "total_obligated": total_obligated,
        "attributed_total_obligated": attributed_total_obligated,
        "unattributed_total_obligated": unmatched_total_obligated,
        "absolute_total_obligated": round(absolute_obligation_denominator, 2),
        "attributed_absolute_obligated": round(attributed_absolute_obligated, 2),
        "obligation_attribution_rate": obligation_attribution_rate,
        "minimum_record_coverage": active_thresholds.minimum_record_coverage,
        "minimum_obligation_coverage": active_thresholds.minimum_obligation_coverage,
        "publication_status": publication_status,
        "warning_flags": warning_flags,
    }
    for status in ATTRIBUTION_STATUSES[1:]:
        status_row = coverage_by_status.loc[
            coverage_by_status["county_attribution_status"].eq(status)
        ].iloc[0]
        summary[f"{status}_record_count"] = int(status_row["record_count"])
        summary[f"{status}_total_obligated"] = status_row["total_obligated"]

    return CountyCoverageResult(
        coverage_by_status=coverage_by_status,
        unmatched_projects=unmatched,
        summary=summary,
    )
