"""Transparent reconciliation for FEMA Public Assistance project data."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

PROJECT_KEY = ("disasterNumber", "gmProjectId")
MONEY_COLUMNS = ("projectAmount", "federalShareObligated", "totalObligated")
DUPLICATE_COMPARISON_COLUMNS = (
    "stateAbbreviation",
    "county",
    "stateNumberCode",
    "countyCode",
    "county_fips",
    "county_attribution_status",
    "damageCategoryCode",
    "projectStatus",
    *MONEY_COLUMNS,
    "declarationDate",
    "firstObligationDate",
    "lastObligationDate",
)


@dataclass(frozen=True)
class ReconciliationTolerance:
    """Dollar tolerance used when comparing independently aggregated totals."""

    absolute_dollars: float = 0.01
    relative: float = 1e-9

    def __post_init__(self) -> None:
        if self.absolute_dollars < 0:
            raise ValueError("absolute_dollars must be nonnegative")
        if self.relative < 0:
            raise ValueError("relative must be nonnegative")


@dataclass(frozen=True)
class PAReconciliationResult:
    """Auditable outputs from one Public Assistance reconciliation run."""

    curated_projects: pd.DataFrame
    duplicate_projects: pd.DataFrame
    disaster_totals: pd.DataFrame
    state_totals: pd.DataFrame
    summary: dict[str, int | float | None]


def _require_columns(frame: pd.DataFrame, columns: Sequence[str]) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"Public Assistance reconciliation data are missing fields: {missing}")


def find_duplicate_projects(frame: pd.DataFrame) -> pd.DataFrame:
    """Return duplicate project keys and identify conflicting material fields."""

    output_columns = [
        *PROJECT_KEY,
        "duplicate_record_count",
        "is_conflicting",
        "conflicting_fields",
    ]
    if frame.empty:
        return pd.DataFrame(columns=output_columns)

    _require_columns(frame, [*PROJECT_KEY, *DUPLICATE_COMPARISON_COLUMNS])
    identified = frame.dropna(subset=list(PROJECT_KEY))
    rows: list[dict[str, object]] = []
    for key, group in identified.groupby(list(PROJECT_KEY), dropna=False, sort=True):
        if len(group) < 2:
            continue
        conflicting_fields = [
            column
            for column in DUPLICATE_COMPARISON_COLUMNS
            if group[column].nunique(dropna=False) > 1
        ]
        rows.append(
            {
                "disasterNumber": key[0],
                "gmProjectId": key[1],
                "duplicate_record_count": len(group),
                "is_conflicting": bool(conflicting_fields),
                "conflicting_fields": ",".join(conflicting_fields),
            }
        )
    return pd.DataFrame(rows, columns=output_columns)


def curate_pa_projects(
    frame: pd.DataFrame,
    duplicate_projects: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Collapse exact duplicates and exclude conflicting project-key groups.

    Records without a complete project key are retained because treating them as
    duplicates would require an unsupported identity assumption.
    """

    if frame.empty:
        return frame.copy()
    _require_columns(frame, PROJECT_KEY)
    duplicates = (
        find_duplicate_projects(frame) if duplicate_projects is None else duplicate_projects
    )

    conflicting = duplicates.loc[duplicates["is_conflicting"], list(PROJECT_KEY)]
    if conflicting.empty:
        conflict_mask = pd.Series(False, index=frame.index)
    else:
        frame_keys = pd.MultiIndex.from_frame(frame[list(PROJECT_KEY)])
        conflict_keys = pd.MultiIndex.from_frame(conflicting)
        conflict_mask = pd.Series(frame_keys.isin(conflict_keys), index=frame.index)

    safe = frame.loc[~conflict_mask]
    has_key = safe[list(PROJECT_KEY)].notna().all(axis=1)
    identified = safe.loc[has_key].drop_duplicates(subset=list(PROJECT_KEY), keep="first")
    unidentified = safe.loc[~has_key]
    return pd.concat([identified, unidentified]).sort_index().reset_index(drop=True)


def _sum_if_present(values: pd.Series) -> float:
    return values.sum(min_count=1)


def _aggregate_totals(
    frame: pd.DataFrame,
    group_columns: Sequence[str],
    prefix: str,
) -> pd.DataFrame:
    output_columns = [
        *group_columns,
        f"{prefix}_record_count",
        f"{prefix}_project_count",
        *(f"{prefix}_{column}" for column in MONEY_COLUMNS),
    ]
    if frame.empty:
        return pd.DataFrame(columns=output_columns)

    _require_columns(frame, [*group_columns, *PROJECT_KEY, *MONEY_COLUMNS])
    aggregated = (
        frame.groupby(list(group_columns), as_index=False, dropna=False)
        .agg(
            record_count=("disasterNumber", "size"),
            project_count=("gmProjectId", "nunique"),
            projectAmount=("projectAmount", _sum_if_present),
            federalShareObligated=("federalShareObligated", _sum_if_present),
            totalObligated=("totalObligated", _sum_if_present),
        )
        .rename(
            columns={
                "record_count": f"{prefix}_record_count",
                "project_count": f"{prefix}_project_count",
                **{column: f"{prefix}_{column}" for column in MONEY_COLUMNS},
            }
        )
    )
    return aggregated[output_columns]


def reconcile_pa_totals(
    source: pd.DataFrame,
    curated: pd.DataFrame,
    group_columns: Sequence[str],
    *,
    tolerance: ReconciliationTolerance | None = None,
) -> pd.DataFrame:
    """Compare independently aggregated source and curated funding totals."""

    if not group_columns:
        raise ValueError("group_columns must contain at least one field")
    active_tolerance = tolerance or ReconciliationTolerance()
    source_totals = _aggregate_totals(source, group_columns, "source")
    curated_totals = _aggregate_totals(curated, group_columns, "curated")
    table = source_totals.merge(curated_totals, on=list(group_columns), how="outer")

    source_absent = table["source_record_count"].isna()
    curated_absent = table["curated_record_count"].isna()
    for prefix, absent in (("source", source_absent), ("curated", curated_absent)):
        for column in ("record_count", "project_count"):
            name = f"{prefix}_{column}"
            table[name] = table[name].astype("Int64").fillna(0).astype("int64")
        for column in MONEY_COLUMNS:
            table.loc[absent, f"{prefix}_{column}"] = 0.0

    table["record_count_variance"] = (
        table["curated_record_count"] - table["source_record_count"]
    )
    table["project_count_variance"] = (
        table["curated_project_count"] - table["source_project_count"]
    )
    matched = table["record_count_variance"].eq(0) & table["project_count_variance"].eq(0)

    for column in MONEY_COLUMNS:
        source_column = f"source_{column}"
        curated_column = f"curated_{column}"
        variance_column = f"{column}_variance"
        tolerance_column = f"{column}_within_tolerance"
        variance = table[curated_column] - table[source_column]
        threshold = (table[source_column].abs() * active_tolerance.relative).clip(
            lower=active_tolerance.absolute_dollars
        )
        both_missing = table[source_column].isna() & table[curated_column].isna()
        one_missing = table[source_column].isna() ^ table[curated_column].isna()
        within_tolerance = both_missing | (~one_missing & variance.abs().le(threshold))
        table[variance_column] = variance
        table[tolerance_column] = within_tolerance
        matched &= within_tolerance

    table["reconciliation_status"] = matched.map({True: "matched", False: "variance"})
    money_output_columns = [
        column
        for column in table.columns
        if any(token in column for token in MONEY_COLUMNS)
        and not column.endswith("_within_tolerance")
    ]
    table[money_output_columns] = table[money_output_columns].round(2)
    return table.sort_values(list(group_columns)).reset_index(drop=True)


def _sum_or_none(frame: pd.DataFrame, column: str) -> float | None:
    value = frame[column].sum(min_count=1)
    return None if pd.isna(value) else round(float(value), 2)


def _difference(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return round(right - left, 2)


def reconcile_pa_projects(
    frame: pd.DataFrame,
    *,
    tolerance: ReconciliationTolerance | None = None,
) -> PAReconciliationResult:
    """Build curated projects, duplicate diagnostics, and reconciliation tables."""

    active_tolerance = tolerance or ReconciliationTolerance()
    _require_columns(
        frame,
        [*PROJECT_KEY, *DUPLICATE_COMPARISON_COLUMNS, "is_county_attributed"],
    )
    duplicates = find_duplicate_projects(frame)
    curated = curate_pa_projects(frame, duplicates)
    disaster_totals = reconcile_pa_totals(
        frame,
        curated,
        ["stateAbbreviation", "disasterNumber"],
        tolerance=active_tolerance,
    )
    state_totals = reconcile_pa_totals(
        frame,
        curated,
        ["stateAbbreviation"],
        tolerance=active_tolerance,
    )

    conflicting_keys = duplicates.loc[duplicates["is_conflicting"], list(PROJECT_KEY)]
    if conflicting_keys.empty:
        excluded_conflict_record_count = 0
    else:
        frame_keys = pd.MultiIndex.from_frame(frame[list(PROJECT_KEY)])
        conflict_index = pd.MultiIndex.from_frame(conflicting_keys)
        excluded_conflict_record_count = int(frame_keys.isin(conflict_index).sum())

    source_totals = {column: _sum_or_none(frame, column) for column in MONEY_COLUMNS}
    curated_totals = {column: _sum_or_none(curated, column) for column in MONEY_COLUMNS}
    summary: dict[str, int | float | None] = {
        "source_record_count": len(frame),
        "curated_record_count": len(curated),
        "source_unique_project_count": int(
            frame.dropna(subset=list(PROJECT_KEY)).drop_duplicates(list(PROJECT_KEY)).shape[0]
        ),
        "curated_unique_project_count": int(
            curated.dropna(subset=list(PROJECT_KEY)).drop_duplicates(list(PROJECT_KEY)).shape[0]
        ),
        "missing_project_id_record_count": int(frame["gmProjectId"].isna().sum()),
        "duplicate_key_count": len(duplicates),
        "conflicting_key_count": int(duplicates["is_conflicting"].sum()),
        "excluded_conflict_record_count": excluded_conflict_record_count,
        "dropped_exact_duplicate_record_count": (
            len(frame) - excluded_conflict_record_count - len(curated)
        ),
        "disaster_variance_count": int(
            disaster_totals["reconciliation_status"].eq("variance").sum()
        ),
        "state_variance_count": int(
            state_totals["reconciliation_status"].eq("variance").sum()
        ),
        "absolute_tolerance_dollars": active_tolerance.absolute_dollars,
        "relative_tolerance": active_tolerance.relative,
    }
    for column in MONEY_COLUMNS:
        summary[f"source_{column}"] = source_totals[column]
        summary[f"curated_{column}"] = curated_totals[column]
        summary[f"{column}_variance"] = _difference(
            source_totals[column], curated_totals[column]
        )

    return PAReconciliationResult(
        curated_projects=curated,
        duplicate_projects=duplicates,
        disaster_totals=disaster_totals,
        state_totals=state_totals,
        summary=summary,
    )
