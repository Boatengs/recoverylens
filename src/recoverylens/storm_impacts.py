"""Auditable injury and fatality aggregation for NOAA Storm Events."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from numbers import Integral, Real

import pandas as pd

from .noaa import NOAAStormEventsError, VerifiedStormEventsFile
from .storm_damage import DETAIL_IDENTITY_COLUMNS, IMPACT_DETAIL_COLUMNS, SOURCE_COLUMNS

MAX_INT64 = 9_223_372_036_854_775_807
COUNT_STATUSES = ("parsed", "reported_zero", "missing", "invalid")
_COUNT_PATTERN = re.compile(r"^\d+$")

FATALITY_COLUMNS = (
    "FAT_YEARMONTH",
    "FATALITY_ID",
    "EVENT_ID",
    "FATALITY_TYPE",
)
FATALITY_SOURCE_COLUMNS = (*SOURCE_COLUMNS, "source_row_number")
ANNUAL_IMPACT_COLUMNS = (
    "data_year",
    "included_event_count",
    "complete_injury_event_count",
    "complete_death_event_count",
    "known_direct_injuries",
    "known_indirect_injuries",
    "known_total_injuries",
    "known_direct_deaths",
    "known_indirect_deaths",
    "known_total_deaths",
    "included_fatality_record_count",
    "fatality_roster_coverage_rate",
    "fatality_roster_count_variance",
    "unmatched_fatality_record_count",
    "fatality_reconciliation_matched_event_count",
    "fatality_reconciliation_mismatch_event_count",
)


@dataclass(frozen=True)
class ImpactCount:
    """One raw NOAA impact count and its conservative interpretation."""

    raw_value: str | None
    count: int | None
    status: str


@dataclass(frozen=True)
class StormImpactResult:
    """Event impacts, annual aggregates, unmatched fatalities, and diagnostics."""

    events: pd.DataFrame
    by_year: pd.DataFrame
    unmatched_fatalities: pd.DataFrame
    summary: dict[str, object]


def parse_impact_count(value: object) -> ImpactCount:
    """Parse a nonnegative NOAA injury or death count without imputation."""

    if value is None or bool(pd.isna(value)):
        return ImpactCount(raw_value=None, count=None, status="missing")
    raw_value = str(value)
    if isinstance(value, bool):
        return ImpactCount(raw_value=raw_value, count=None, status="invalid")
    if isinstance(value, Integral):
        count = int(value)
        if count < 0 or count > MAX_INT64:
            return ImpactCount(raw_value=raw_value, count=None, status="invalid")
        return ImpactCount(
            raw_value=raw_value,
            count=count,
            status="reported_zero" if count == 0 else "parsed",
        )
    if isinstance(value, Real):
        numeric = float(value)
        if not math.isfinite(numeric) or not numeric.is_integer():
            return ImpactCount(raw_value=raw_value, count=None, status="invalid")
        count = int(numeric)
        if count < 0 or count > MAX_INT64:
            return ImpactCount(raw_value=raw_value, count=None, status="invalid")
        return ImpactCount(
            raw_value=raw_value,
            count=count,
            status="reported_zero" if count == 0 else "parsed",
        )
    normalized = raw_value.strip()
    if not normalized:
        return ImpactCount(raw_value=raw_value, count=None, status="missing")
    if _COUNT_PATTERN.fullmatch(normalized) is None:
        return ImpactCount(raw_value=raw_value, count=None, status="invalid")
    count = int(normalized)
    if count > MAX_INT64:
        return ImpactCount(raw_value=raw_value, count=None, status="invalid")
    return ImpactCount(
        raw_value=raw_value,
        count=count,
        status="reported_zero" if count == 0 else "parsed",
    )


def _identifier(value: object) -> int | None:
    if value is None or bool(pd.isna(value)):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, Integral):
        number = int(value)
        return number if 0 <= number <= MAX_INT64 else None
    if isinstance(value, Real):
        numeric = float(value)
        if not math.isfinite(numeric) or not numeric.is_integer():
            return None
        number = int(numeric)
        return number if 0 <= number <= MAX_INT64 else None
    normalized = str(value).strip()
    if _COUNT_PATTERN.fullmatch(normalized) is None:
        return None
    number = int(normalized)
    return number if number <= MAX_INT64 else None


def read_storm_event_fatalities(files: tuple[VerifiedStormEventsFile, ...]) -> pd.DataFrame:
    """Read checksum-verified NOAA fatality files with row-level provenance."""

    if not files:
        raise ValueError("At least one verified NOAA fatalities file is required")
    frames: list[pd.DataFrame] = []
    for verified in files:
        if verified.source.dataset != "fatalities":
            raise ValueError(f"Expected a fatalities file, received: {verified.source.dataset}")
        try:
            frame = pd.read_csv(
                verified.path,
                compression="gzip",
                dtype="string",
                keep_default_na=False,
                low_memory=False,
                usecols=list(FATALITY_COLUMNS),
            )
        except (OSError, UnicodeError, ValueError, pd.errors.ParserError) as exc:
            raise NOAAStormEventsError(
                f"Could not read NOAA fatalities file: {verified.path.name}"
            ) from exc
        frame = frame.assign(
            source_filename=verified.source.filename,
            source_data_year=verified.source.data_year,
            source_schema_version=verified.source.schema_version,
            source_created_on=verified.source.created_on.isoformat(),
            source_retrieved_at=verified.manifest_record.get("retrieved_at"),
            source_row_number=pd.array(range(2, len(frame) + 2), dtype="Int64"),
        )
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _parsed_count_columns(values: pd.Series, prefix: str) -> pd.DataFrame:
    parsed = [parse_impact_count(value) for value in values]
    return pd.DataFrame(
        {
            f"{prefix}_count": pd.array([item.count for item in parsed], dtype="Int64"),
            f"{prefix}_status": pd.array([item.status for item in parsed], dtype="string"),
        },
        index=values.index,
    )


def _share(numerator: int, denominator: int) -> float | None:
    if not denominator:
        return None
    return round(numerator / denominator, 6)


def _sum_or_none(values: pd.Series) -> int | None:
    observed = values.dropna()
    if observed.empty:
        return None
    return int(observed.sum())


def _normalize_events(details: pd.DataFrame) -> pd.DataFrame:
    required = {*DETAIL_IDENTITY_COLUMNS, *IMPACT_DETAIL_COLUMNS}
    missing = sorted(required - set(details.columns))
    if missing:
        raise ValueError(f"NOAA details impact data are missing fields: {missing}")
    source = details.copy()
    for column in SOURCE_COLUMNS:
        if column not in source:
            source[column] = pd.NA
    events = pd.DataFrame(
        {
            "episode_id": pd.array(
                [_identifier(value) for value in source["EPISODE_ID"]], dtype="Int64"
            ),
            "event_id": pd.array(
                [_identifier(value) for value in source["EVENT_ID"]], dtype="Int64"
            ),
            "event_year": pd.array([_identifier(value) for value in source["YEAR"]], dtype="Int64"),
            "state": source["STATE"].astype("string").str.strip(),
            "state_fips": source["STATE_FIPS"].astype("string").str.strip(),
            "event_type": source["EVENT_TYPE"].astype("string").str.strip(),
            "cz_type": source["CZ_TYPE"].astype("string").str.strip(),
            "cz_fips": source["CZ_FIPS"].astype("string").str.strip(),
            "cz_name": source["CZ_NAME"].astype("string").str.strip(),
            "source_filename": source["source_filename"].astype("string"),
            "source_data_year": pd.array(
                [_identifier(value) for value in source["source_data_year"]],
                dtype="Int64",
            ),
            "source_schema_version": source["source_schema_version"].astype("string"),
            "source_created_on": source["source_created_on"].astype("string"),
            "source_retrieved_at": source["source_retrieved_at"].astype("string"),
        }
    )
    impact_names = {
        "INJURIES_DIRECT": "injuries_direct",
        "INJURIES_INDIRECT": "injuries_indirect",
        "DEATHS_DIRECT": "deaths_direct",
        "DEATHS_INDIRECT": "deaths_indirect",
    }
    for source_column, prefix in impact_names.items():
        events[f"{prefix}_raw"] = source[source_column].astype("string")
        events = pd.concat(
            [events, _parsed_count_columns(events[f"{prefix}_raw"], prefix)],
            axis=1,
        )

    injury_statuses = ["injuries_direct_status", "injuries_indirect_status"]
    death_statuses = ["deaths_direct_status", "deaths_indirect_status"]
    valid_statuses = ("parsed", "reported_zero")
    events["known_total_injuries"] = events[
        ["injuries_direct_count", "injuries_indirect_count"]
    ].sum(axis=1, min_count=1)
    events["known_total_deaths"] = events[["deaths_direct_count", "deaths_indirect_count"]].sum(
        axis=1, min_count=1
    )
    events["is_injury_count_complete"] = events[injury_statuses].isin(valid_statuses).all(axis=1)
    events["is_death_count_complete"] = events[death_statuses].isin(valid_statuses).all(axis=1)
    events["is_source_year_consistent"] = (
        events["event_year"].notna()
        & events["source_data_year"].notna()
        & events["event_year"].eq(events["source_data_year"])
    )
    duplicate_event = events["event_id"].notna() & events["event_id"].duplicated(keep=False)
    events["is_duplicate_event_id"] = duplicate_event
    events["aggregation_status"] = "included"
    events.loc[~events["is_source_year_consistent"], "aggregation_status"] = (
        "source_year_inconsistent"
    )
    events.loc[duplicate_event, "aggregation_status"] = "duplicate_event_id"
    events.loc[events["event_id"].isna(), "aggregation_status"] = "missing_event_id"
    return events.sort_values(
        ["source_data_year", "event_id", "source_filename"],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)


def _normalize_fatalities(frame: pd.DataFrame) -> pd.DataFrame:
    required = set(FATALITY_COLUMNS)
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"NOAA fatality data are missing fields: {missing}")
    source = frame.copy()
    for column in FATALITY_SOURCE_COLUMNS:
        if column not in source:
            source[column] = pd.NA
    yearmonth = source["FAT_YEARMONTH"].astype("string").str.strip()
    valid_yearmonth = yearmonth.str.fullmatch(r"\d{6}", na=False)
    fatalities = pd.DataFrame(
        {
            "fatality_id": pd.array(
                [_identifier(value) for value in source["FATALITY_ID"]], dtype="Int64"
            ),
            "event_id": pd.array(
                [_identifier(value) for value in source["EVENT_ID"]], dtype="Int64"
            ),
            "fatality_type_raw": source["FATALITY_TYPE"].astype("string"),
            "fatality_type": source["FATALITY_TYPE"]
            .astype("string")
            .str.strip()
            .str.upper()
            .map({"D": "direct", "I": "indirect"}),
            "fatality_year": pd.to_numeric(
                yearmonth.str[:4].where(valid_yearmonth), errors="coerce"
            ).astype("Int64"),
            "source_filename": source["source_filename"].astype("string"),
            "source_data_year": pd.array(
                [_identifier(value) for value in source["source_data_year"]], dtype="Int64"
            ),
            "source_schema_version": source["source_schema_version"].astype("string"),
            "source_created_on": source["source_created_on"].astype("string"),
            "source_retrieved_at": source["source_retrieved_at"].astype("string"),
            "source_row_number": pd.array(
                [_identifier(value) for value in source["source_row_number"]], dtype="Int64"
            ),
        }
    )
    normalized_type = source["FATALITY_TYPE"].astype("string").str.strip()
    fatalities["fatality_type_status"] = "valid"
    fatalities.loc[normalized_type.eq(""), "fatality_type_status"] = "missing"
    fatalities.loc[
        normalized_type.ne("") & fatalities["fatality_type"].isna(),
        "fatality_type_status",
    ] = "invalid"
    fatalities["is_source_year_consistent"] = (
        fatalities["fatality_year"].notna()
        & fatalities["source_data_year"].notna()
        & fatalities["fatality_year"].eq(fatalities["source_data_year"])
    )
    duplicate = fatalities["fatality_id"].notna() & fatalities["fatality_id"].duplicated(keep=False)
    fatalities["is_duplicate_fatality_id"] = duplicate
    conflicting_ids: set[int] = set()
    for fatality_id, group in fatalities.loc[duplicate].groupby("fatality_id", sort=True):
        signatures = {
            (
                None if pd.isna(row.event_id) else int(row.event_id),
                None if pd.isna(row.fatality_type) else str(row.fatality_type),
            )
            for row in group.itertuples()
        }
        if len(signatures) > 1:
            conflicting_ids.add(int(fatality_id))
    fatalities["is_conflicting_fatality_id"] = fatalities["fatality_id"].isin(conflicting_ids)
    fatalities["aggregation_status"] = "candidate"
    fatalities.loc[~fatalities["is_source_year_consistent"], "aggregation_status"] = (
        "source_year_inconsistent"
    )
    fatalities.loc[fatalities["fatality_type_status"].eq("invalid"), "aggregation_status"] = (
        "invalid_fatality_type"
    )
    fatalities.loc[fatalities["fatality_type_status"].eq("missing"), "aggregation_status"] = (
        "missing_fatality_type"
    )
    fatalities.loc[fatalities["event_id"].isna(), "aggregation_status"] = "missing_event_id"
    fatalities.loc[duplicate, "aggregation_status"] = "duplicate_fatality_id"
    fatalities.loc[fatalities["fatality_id"].isna(), "aggregation_status"] = "missing_fatality_id"
    return fatalities.sort_values(
        ["source_data_year", "source_filename", "source_row_number", "fatality_id"],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)


def _link_fatalities(
    events: pd.DataFrame,
    fatalities: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    included_ids = set(
        int(value)
        for value in events.loc[events["aggregation_status"].eq("included"), "event_id"]
        .dropna()
        .unique()
    )
    ambiguous_ids = set(
        int(value)
        for value in events.loc[events["is_duplicate_event_id"], "event_id"].dropna().unique()
    )
    linked = fatalities.copy()
    candidate = linked["aggregation_status"].eq("candidate")
    linked.loc[candidate & linked["event_id"].isin(ambiguous_ids), "aggregation_status"] = (
        "ambiguous_event_id"
    )
    candidate = linked["aggregation_status"].eq("candidate")
    linked.loc[candidate & ~linked["event_id"].isin(included_ids), "aggregation_status"] = (
        "unmatched_event_id"
    )
    linked.loc[linked["aggregation_status"].eq("candidate"), "aggregation_status"] = "included"

    included = linked.loc[linked["aggregation_status"].eq("included")]
    roster = (
        included.assign(record_count=1)
        .pivot_table(
            index="event_id",
            columns="fatality_type",
            values="record_count",
            aggfunc="sum",
            fill_value=0,
        )
        .rename(columns={"direct": "roster_direct_deaths", "indirect": "roster_indirect_deaths"})
    )
    for column in ("roster_direct_deaths", "roster_indirect_deaths"):
        if column not in roster:
            roster[column] = 0
    roster = roster[["roster_direct_deaths", "roster_indirect_deaths"]].reset_index()
    merged = events.merge(roster, on="event_id", how="left", validate="many_to_one")
    for column in ("roster_direct_deaths", "roster_indirect_deaths"):
        merged[column] = merged[column].fillna(0).astype("Int64")
    merged["roster_total_deaths"] = (
        merged["roster_direct_deaths"] + merged["roster_indirect_deaths"]
    )
    eligible = merged["aggregation_status"].eq("included")
    complete = merged["is_death_count_complete"]
    direct_match = merged["deaths_direct_count"].eq(merged["roster_direct_deaths"])
    indirect_match = merged["deaths_indirect_count"].eq(merged["roster_indirect_deaths"])
    merged["fatality_reconciliation_status"] = "not_evaluated"
    merged.loc[eligible & ~complete, "fatality_reconciliation_status"] = "details_incomplete"
    merged.loc[
        eligible & complete & direct_match & indirect_match,
        "fatality_reconciliation_status",
    ] = "matched"
    merged.loc[
        eligible & complete & ~(direct_match & indirect_match),
        "fatality_reconciliation_status",
    ] = "mismatch"
    merged["direct_death_variance"] = (
        merged["roster_direct_deaths"] - merged["deaths_direct_count"]
    ).where(eligible & complete)
    merged["indirect_death_variance"] = (
        merged["roster_indirect_deaths"] - merged["deaths_indirect_count"]
    ).where(eligible & complete)
    merged["total_death_variance"] = (
        merged["roster_total_deaths"] - merged["known_total_deaths"]
    ).where(eligible & complete)
    merged = merged.sort_values(
        ["source_data_year", "event_id", "source_filename"],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)
    unmatched = linked.loc[~linked["aggregation_status"].eq("included")].reset_index(drop=True)
    return merged, linked, unmatched


def _impact_summary(
    events: pd.DataFrame,
    fatalities: pd.DataFrame,
    unmatched: pd.DataFrame,
) -> dict[str, object]:
    included_events = events.loc[events["aggregation_status"].eq("included")]
    included_fatalities = fatalities.loc[fatalities["aggregation_status"].eq("included")]
    impact_status_columns = [
        "injuries_direct_status",
        "injuries_indirect_status",
        "deaths_direct_status",
        "deaths_indirect_status",
    ]
    invalid_event = events[impact_status_columns].eq("invalid").any(axis=1)
    missing_event = events[impact_status_columns].eq("missing").any(axis=1)
    matched_count = int(events["fatality_reconciliation_status"].eq("matched").sum())
    mismatch_count = int(events["fatality_reconciliation_status"].eq("mismatch").sum())
    comparison_count = matched_count + mismatch_count
    duplicate_fatality_ids = int(
        fatalities.loc[fatalities["is_duplicate_fatality_id"], "fatality_id"].nunique()
    )
    conflicting_fatality_ids = int(
        fatalities.loc[fatalities["is_conflicting_fatality_id"], "fatality_id"].nunique()
    )
    summary: dict[str, object] = {
        "input_event_record_count": len(events),
        "included_event_count": len(included_events),
        "unique_event_count": int(events["event_id"].nunique()),
        "missing_event_id_record_count": int(events["event_id"].isna().sum()),
        "duplicate_event_id_count": int(
            events.loc[events["is_duplicate_event_id"], "event_id"].nunique()
        ),
        "duplicate_event_id_record_count": int(events["is_duplicate_event_id"].sum()),
        "event_source_year_inconsistency_count": int((~events["is_source_year_consistent"]).sum()),
        "invalid_impact_count_event_count": int(invalid_event.sum()),
        "missing_impact_count_event_count": int(missing_event.sum()),
        "complete_injury_event_count": int(included_events["is_injury_count_complete"].sum()),
        "complete_injury_event_rate": _share(
            int(included_events["is_injury_count_complete"].sum()), len(included_events)
        ),
        "complete_death_event_count": int(included_events["is_death_count_complete"].sum()),
        "complete_death_event_rate": _share(
            int(included_events["is_death_count_complete"].sum()), len(included_events)
        ),
        "known_direct_injuries": _sum_or_none(included_events["injuries_direct_count"]),
        "known_indirect_injuries": _sum_or_none(included_events["injuries_indirect_count"]),
        "known_total_injuries": _sum_or_none(included_events["known_total_injuries"]),
        "known_direct_deaths": _sum_or_none(included_events["deaths_direct_count"]),
        "known_indirect_deaths": _sum_or_none(included_events["deaths_indirect_count"]),
        "known_total_deaths": _sum_or_none(included_events["known_total_deaths"]),
        "fatality_record_count": len(fatalities),
        "included_fatality_record_count": len(included_fatalities),
        "unmatched_fatality_record_count": len(unmatched),
        "roster_direct_death_count": int(included_fatalities["fatality_type"].eq("direct").sum()),
        "roster_indirect_death_count": int(
            included_fatalities["fatality_type"].eq("indirect").sum()
        ),
        "duplicate_fatality_id_count": duplicate_fatality_ids,
        "conflicting_fatality_id_count": conflicting_fatality_ids,
        "missing_fatality_id_record_count": int(fatalities["fatality_id"].isna().sum()),
        "missing_fatality_event_id_record_count": int(fatalities["event_id"].isna().sum()),
        "invalid_fatality_type_record_count": int(
            fatalities["fatality_type_status"].eq("invalid").sum()
        ),
        "missing_fatality_type_record_count": int(
            fatalities["fatality_type_status"].eq("missing").sum()
        ),
        "fatality_source_year_inconsistency_count": int(
            (~fatalities["is_source_year_consistent"]).sum()
        ),
        "fatality_reconciliation_matched_event_count": matched_count,
        "fatality_reconciliation_mismatch_event_count": mismatch_count,
        "fatality_reconciliation_details_incomplete_event_count": int(
            events["fatality_reconciliation_status"].eq("details_incomplete").sum()
        ),
        "fatality_reconciliation_rate": _share(matched_count, comparison_count),
        "details_source_filenames": sorted(
            str(value) for value in events["source_filename"].dropna().unique()
        ),
        "fatality_source_filenames": sorted(
            str(value) for value in fatalities["source_filename"].dropna().unique()
        ),
        "source_data_years": sorted(
            {
                *(int(value) for value in events["source_data_year"].dropna().unique()),
                *(int(value) for value in fatalities["source_data_year"].dropna().unique()),
            }
        ),
    }
    known_total_deaths = summary["known_total_deaths"]
    if isinstance(known_total_deaths, int) and known_total_deaths > 0:
        summary["fatality_roster_coverage_rate"] = _share(
            len(included_fatalities), known_total_deaths
        )
        summary["fatality_roster_count_variance"] = len(included_fatalities) - known_total_deaths
    else:
        summary["fatality_roster_coverage_rate"] = None
        summary["fatality_roster_count_variance"] = None
    warning_flags: list[str] = []
    if not len(events):
        warning_flags.append("no_events")
    if len(events) and not len(included_events):
        warning_flags.append("no_included_events")
    for flag, condition in (
        ("missing_event_ids", summary["missing_event_id_record_count"]),
        ("duplicate_event_ids", summary["duplicate_event_id_count"]),
        ("event_source_year_inconsistencies", summary["event_source_year_inconsistency_count"]),
        ("invalid_impact_counts", summary["invalid_impact_count_event_count"]),
        ("missing_impact_counts", summary["missing_impact_count_event_count"]),
        ("duplicate_fatality_ids", duplicate_fatality_ids),
        ("conflicting_fatality_ids", conflicting_fatality_ids),
        ("missing_fatality_ids", summary["missing_fatality_id_record_count"]),
        (
            "missing_fatality_event_ids",
            summary["missing_fatality_event_id_record_count"],
        ),
        ("invalid_fatality_types", summary["invalid_fatality_type_record_count"]),
        ("missing_fatality_types", summary["missing_fatality_type_record_count"]),
        (
            "fatality_source_year_inconsistencies",
            summary["fatality_source_year_inconsistency_count"],
        ),
        ("unmatched_fatality_records", len(unmatched)),
        ("fatality_count_mismatches", mismatch_count),
        (
            "incomplete_death_counts",
            summary["fatality_reconciliation_details_incomplete_event_count"],
        ),
    ):
        if condition:
            warning_flags.append(flag)
    blocking_flags = {"no_events", "no_included_events"}
    if blocking_flags.intersection(warning_flags):
        publication_status = "blocked"
    elif warning_flags:
        publication_status = "warning"
    else:
        publication_status = "ready"
    summary["publication_status"] = publication_status
    summary["warning_flags"] = warning_flags
    return summary


def _annual_summary(
    events: pd.DataFrame,
    fatalities: pd.DataFrame,
    unmatched: pd.DataFrame,
) -> pd.DataFrame:
    years = sorted(
        {
            *(int(value) for value in events["source_data_year"].dropna().unique()),
            *(int(value) for value in fatalities["source_data_year"].dropna().unique()),
        }
    )
    rows: list[dict[str, object]] = []
    for year in years:
        year_events = events.loc[
            events["source_data_year"].eq(year) & events["aggregation_status"].eq("included")
        ]
        year_fatalities = fatalities.loc[
            fatalities["source_data_year"].eq(year)
            & fatalities["aggregation_status"].eq("included")
        ]
        year_unmatched = unmatched.loc[unmatched["source_data_year"].eq(year)]
        known_total_deaths = _sum_or_none(year_events["known_total_deaths"])
        if isinstance(known_total_deaths, int) and known_total_deaths > 0:
            roster_coverage = _share(len(year_fatalities), known_total_deaths)
            roster_variance = len(year_fatalities) - known_total_deaths
        else:
            roster_coverage = None
            roster_variance = None
        rows.append(
            {
                "data_year": year,
                "included_event_count": len(year_events),
                "complete_injury_event_count": int(year_events["is_injury_count_complete"].sum()),
                "complete_death_event_count": int(year_events["is_death_count_complete"].sum()),
                "known_direct_injuries": _sum_or_none(year_events["injuries_direct_count"]),
                "known_indirect_injuries": _sum_or_none(year_events["injuries_indirect_count"]),
                "known_total_injuries": _sum_or_none(year_events["known_total_injuries"]),
                "known_direct_deaths": _sum_or_none(year_events["deaths_direct_count"]),
                "known_indirect_deaths": _sum_or_none(year_events["deaths_indirect_count"]),
                "known_total_deaths": known_total_deaths,
                "included_fatality_record_count": len(year_fatalities),
                "fatality_roster_coverage_rate": roster_coverage,
                "fatality_roster_count_variance": roster_variance,
                "unmatched_fatality_record_count": len(year_unmatched),
                "fatality_reconciliation_matched_event_count": int(
                    year_events["fatality_reconciliation_status"].eq("matched").sum()
                ),
                "fatality_reconciliation_mismatch_event_count": int(
                    year_events["fatality_reconciliation_status"].eq("mismatch").sum()
                ),
            }
        )
    return pd.DataFrame(rows, columns=ANNUAL_IMPACT_COLUMNS)


def analyze_storm_event_impacts(
    details: pd.DataFrame,
    fatality_records: pd.DataFrame,
) -> StormImpactResult:
    """Aggregate event impacts and reconcile death counts to fatality records."""

    events = _normalize_events(details)
    fatalities = _normalize_fatalities(fatality_records)
    events, fatalities, unmatched = _link_fatalities(events, fatalities)
    summary = _impact_summary(events, fatalities, unmatched)
    return StormImpactResult(
        events=events,
        by_year=_annual_summary(events, fatalities, unmatched),
        unmatched_fatalities=unmatched,
        summary=summary,
    )
