"""Public Assistance obligation-category and timing measures."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

DAMAGE_CATEGORY_LABELS = {
    "A": "Debris Removal",
    "B": "Emergency Protective Measures",
    "C": "Roads and Bridges",
    "D": "Water Control Facilities",
    "E": "Buildings and Equipment",
    "F": "Utilities",
    "G": "Parks, Recreational, and Other Facilities",
    "Z": "Management Costs",
}

DAMAGE_CATEGORY_GROUPS = {
    "A": "emergency_work",
    "B": "emergency_work",
    "C": "permanent_work",
    "D": "permanent_work",
    "E": "permanent_work",
    "F": "permanent_work",
    "G": "permanent_work",
    "Z": "management_costs",
}

REQUIRED_COLUMNS = {
    "disasterNumber",
    "gmProjectId",
    "damageCategoryCode",
    "totalObligated",
    "declarationDate",
    "firstObligationDate",
    "lastObligationDate",
}


@dataclass(frozen=True)
class ObligationMetricsResult:
    """Project details, category aggregates, and run-level timing diagnostics."""

    projects: pd.DataFrame
    category_summary: pd.DataFrame
    summary: dict[str, object]


def _share(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def _quantile(values: pd.Series, quantile: float) -> float | None:
    observed = values.dropna()
    if observed.empty:
        return None
    return round(float(observed.quantile(quantile)), 3)


def _sum_obligated(values: pd.Series) -> float:
    value = values.sum(min_count=1)
    return 0.0 if pd.isna(value) else round(float(value), 2)


def _category_row(
    projects: pd.DataFrame,
    *,
    code: str | None,
    status: str,
) -> dict[str, object]:
    if status == "missing":
        subset = projects.loc[projects["damage_category_status"].eq("missing")]
        label = "Missing category"
        group = "unclassified"
    else:
        subset = projects.loc[projects["damage_category_code"].eq(code)]
        label = DAMAGE_CATEGORY_LABELS.get(str(code), "Unmapped category")
        group = DAMAGE_CATEGORY_GROUPS.get(str(code), "unclassified")

    first = subset["days_to_first_obligation"]
    last = subset["days_to_last_obligation"]
    window = subset["obligation_window_days"]
    obligations = subset["totalObligated"].dropna()
    return {
        "damage_category_code": code,
        "damage_category_label": label,
        "damage_category_group": group,
        "damage_category_status": status,
        "project_count": len(subset),
        "unique_project_count": int(subset["gmProjectId"].nunique()),
        "net_total_obligated": _sum_obligated(subset["totalObligated"]),
        "absolute_total_obligated": round(float(obligations.abs().sum()), 2),
        "valid_first_timing_count": int(first.notna().sum()),
        "first_obligation_days_p25": _quantile(first, 0.25),
        "first_obligation_days_median": _quantile(first, 0.5),
        "first_obligation_days_p75": _quantile(first, 0.75),
        "valid_last_timing_count": int(last.notna().sum()),
        "last_obligation_days_median": _quantile(last, 0.5),
        "valid_window_count": int(window.notna().sum()),
        "obligation_window_days_median": _quantile(window, 0.5),
    }


def analyze_obligation_metrics(frame: pd.DataFrame) -> ObligationMetricsResult:
    """Classify work categories and calculate auditable obligation timing."""

    missing_columns = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing_columns:
        raise ValueError(f"Obligation metrics data are missing fields: {missing_columns}")

    projects = frame.copy()
    category_code = projects["damageCategoryCode"].astype("string").str.strip().str.upper()
    category_code = category_code.mask(category_code.eq(""))
    category_missing = category_code.isna()
    category_mapped = category_code.isin(DAMAGE_CATEGORY_LABELS)
    category_status = pd.Series("unmapped", index=projects.index, dtype="string")
    category_status.loc[category_mapped] = "mapped"
    category_status.loc[category_missing] = "missing"

    category_label = category_code.map(DAMAGE_CATEGORY_LABELS).astype("string")
    category_label.loc[category_status.eq("unmapped")] = "Unmapped category"
    category_label.loc[category_status.eq("missing")] = "Missing category"
    category_group = category_code.map(DAMAGE_CATEGORY_GROUPS).astype("string")
    category_group.loc[~category_status.eq("mapped")] = "unclassified"

    declaration = pd.to_datetime(projects["declarationDate"], errors="coerce", utc=True)
    first = pd.to_datetime(projects["firstObligationDate"], errors="coerce", utc=True)
    last = pd.to_datetime(projects["lastObligationDate"], errors="coerce", utc=True)
    first_before_declaration = declaration.notna() & first.notna() & first.lt(declaration)
    last_before_declaration = declaration.notna() & last.notna() & last.lt(declaration)
    last_before_first = first.notna() & last.notna() & last.lt(first)

    valid_first = declaration.notna() & first.notna() & ~first_before_declaration
    valid_last = declaration.notna() & last.notna() & ~last_before_declaration
    valid_window = first.notna() & last.notna() & ~last_before_first
    timing_complete = valid_first & valid_last & valid_window

    timing_status = pd.Series("complete", index=projects.index, dtype="string")
    timing_status.loc[declaration.isna()] = "missing_declaration_date"
    timing_status.loc[declaration.notna() & first.isna()] = "missing_first_obligation_date"
    timing_status.loc[declaration.notna() & first.notna() & last.isna()] = (
        "missing_last_obligation_date"
    )
    invalid_chronology = first_before_declaration | last_before_declaration | last_before_first
    timing_status.loc[invalid_chronology] = "invalid_chronology"

    projects = projects.assign(
        damage_category_code=category_code,
        damage_category_label=category_label,
        damage_category_group=category_group,
        damage_category_status=category_status,
        first_obligation_before_declaration=first_before_declaration,
        last_obligation_before_declaration=last_before_declaration,
        last_obligation_before_first=last_before_first,
        timing_status=timing_status,
        is_timing_complete=timing_complete,
        days_to_first_obligation=(first - declaration)
        .dt.total_seconds()
        .div(86_400)
        .where(valid_first)
        .round(3)
        .astype("Float64"),
        days_to_last_obligation=(last - declaration)
        .dt.total_seconds()
        .div(86_400)
        .where(valid_last)
        .round(3)
        .astype("Float64"),
        obligation_window_days=(last - first)
        .dt.total_seconds()
        .div(86_400)
        .where(valid_window)
        .round(3)
        .astype("Float64"),
    ).sort_values(
        ["disasterNumber", "gmProjectId"],
        kind="mergesort",
        na_position="last",
    )
    projects = projects.reset_index(drop=True)

    observed_unmapped = sorted(
        str(code)
        for code in projects.loc[
            projects["damage_category_status"].eq("unmapped"),
            "damage_category_code",
        ]
        .dropna()
        .unique()
    )
    rows = [_category_row(projects, code=code, status="mapped") for code in DAMAGE_CATEGORY_LABELS]
    rows.extend(_category_row(projects, code=code, status="unmapped") for code in observed_unmapped)
    if category_missing.any():
        rows.append(_category_row(projects, code=None, status="missing"))
    category_summary = pd.DataFrame(rows)

    project_count = len(projects)
    mapped_count = int(projects["damage_category_status"].eq("mapped").sum())
    missing_category_count = int(projects["damage_category_status"].eq("missing").sum())
    unmapped_category_count = int(projects["damage_category_status"].eq("unmapped").sum())
    valid_first_count = int(projects["days_to_first_obligation"].notna().sum())
    valid_last_count = int(projects["days_to_last_obligation"].notna().sum())
    valid_window_count = int(projects["obligation_window_days"].notna().sum())
    invalid_chronology_count = int(invalid_chronology.sum())

    warning_flags: list[str] = []
    if not project_count:
        warning_flags.append("no_curated_projects")
    if missing_category_count:
        warning_flags.append("missing_damage_categories")
    if unmapped_category_count:
        warning_flags.append("unmapped_damage_categories")
    for flag, count in (
        ("missing_declaration_dates", int(declaration.isna().sum())),
        ("missing_first_obligation_dates", int(first.isna().sum())),
        ("missing_last_obligation_dates", int(last.isna().sum())),
        ("invalid_timing_chronology", invalid_chronology_count),
    ):
        if count:
            warning_flags.append(flag)
    if project_count and not valid_first_count:
        warning_flags.append("no_valid_first_obligation_timing")

    blocking_flags = {"no_curated_projects", "no_valid_first_obligation_timing"}
    if blocking_flags.intersection(warning_flags):
        publication_status = "blocked"
    elif warning_flags:
        publication_status = "warning"
    else:
        publication_status = "ready"

    summary: dict[str, object] = {
        "project_count": project_count,
        "mapped_category_count": mapped_count,
        "missing_category_count": missing_category_count,
        "unmapped_category_count": unmapped_category_count,
        "category_coverage_rate": _share(mapped_count, project_count),
        "missing_declaration_date_count": int(declaration.isna().sum()),
        "missing_first_obligation_date_count": int(first.isna().sum()),
        "missing_last_obligation_date_count": int(last.isna().sum()),
        "first_obligation_before_declaration_count": int(first_before_declaration.sum()),
        "last_obligation_before_declaration_count": int(last_before_declaration.sum()),
        "last_obligation_before_first_count": int(last_before_first.sum()),
        "invalid_chronology_record_count": invalid_chronology_count,
        "valid_first_timing_count": valid_first_count,
        "valid_first_timing_rate": _share(valid_first_count, project_count),
        "valid_last_timing_count": valid_last_count,
        "valid_last_timing_rate": _share(valid_last_count, project_count),
        "valid_window_count": valid_window_count,
        "valid_window_rate": _share(valid_window_count, project_count),
        "complete_timing_count": int(timing_complete.sum()),
        "complete_timing_rate": _share(int(timing_complete.sum()), project_count),
        "first_obligation_days_median": _quantile(projects["days_to_first_obligation"], 0.5),
        "last_obligation_days_median": _quantile(projects["days_to_last_obligation"], 0.5),
        "obligation_window_days_median": _quantile(projects["obligation_window_days"], 0.5),
        "publication_status": publication_status,
        "warning_flags": warning_flags,
    }
    return ObligationMetricsResult(
        projects=projects,
        category_summary=category_summary,
        summary=summary,
    )
