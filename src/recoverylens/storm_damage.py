"""Transparent parsing and summaries for NOAA Storm Events damage estimates."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import pandas as pd

from .noaa import NOAAStormEventsError, VerifiedStormEventsFile

DAMAGE_MULTIPLIERS = {
    None: Decimal("1"),
    "K": Decimal("1000"),
    "M": Decimal("1000000"),
    "B": Decimal("1000000000"),
}
DAMAGE_STATUSES = ("parsed", "reported_zero", "missing", "invalid")
_DAMAGE_PATTERN = re.compile(r"^(?P<amount>(?:\d+(?:\.\d*)?|\.\d+))(?P<suffix>[KMB])?$")

DETAIL_COLUMNS = (
    "EPISODE_ID",
    "EVENT_ID",
    "STATE",
    "STATE_FIPS",
    "YEAR",
    "EVENT_TYPE",
    "CZ_TYPE",
    "CZ_FIPS",
    "CZ_NAME",
    "DAMAGE_PROPERTY",
    "DAMAGE_CROPS",
)
SOURCE_COLUMNS = (
    "source_filename",
    "source_data_year",
    "source_schema_version",
    "source_created_on",
    "source_retrieved_at",
)
ANNUAL_SUMMARY_COLUMNS = (
    "data_year",
    "event_count",
    "unique_event_count",
    "property_parsed_count",
    "property_reported_zero_count",
    "property_missing_count",
    "property_invalid_count",
    "crops_parsed_count",
    "crops_reported_zero_count",
    "crops_missing_count",
    "crops_invalid_count",
    "complete_damage_event_count",
    "known_property_damage_dollars",
    "known_crop_damage_dollars",
    "known_total_damage_dollars",
)


@dataclass(frozen=True)
class DamageAmount:
    """One raw NOAA damage value and its conservative interpretation."""

    raw_value: str | None
    dollars: float | None
    status: str
    suffix: str | None


@dataclass(frozen=True)
class StormDamageResult:
    """Event-level damage fields, annual aggregates, and run diagnostics."""

    events: pd.DataFrame
    by_year: pd.DataFrame
    summary: dict[str, object]


def parse_damage_amount(value: object) -> DamageAmount:
    """Parse a NOAA compact damage estimate without imputing missing values."""

    if value is None or bool(pd.isna(value)):
        return DamageAmount(raw_value=None, dollars=None, status="missing", suffix=None)
    raw_value = str(value)
    normalized = raw_value.strip().upper()
    if not normalized:
        return DamageAmount(raw_value=raw_value, dollars=None, status="missing", suffix=None)
    match = _DAMAGE_PATTERN.fullmatch(normalized)
    if match is None:
        return DamageAmount(raw_value=raw_value, dollars=None, status="invalid", suffix=None)
    suffix = match["suffix"] or None
    try:
        amount = Decimal(match["amount"]) * DAMAGE_MULTIPLIERS[suffix]
        dollars = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        dollar_value = float(dollars)
    except (InvalidOperation, KeyError, OverflowError):
        return DamageAmount(raw_value=raw_value, dollars=None, status="invalid", suffix=suffix)
    if not math.isfinite(dollar_value):
        return DamageAmount(raw_value=raw_value, dollars=None, status="invalid", suffix=suffix)
    status = "reported_zero" if dollars == 0 else "parsed"
    return DamageAmount(
        raw_value=raw_value,
        dollars=dollar_value,
        status=status,
        suffix=suffix,
    )


def read_storm_event_details(files: tuple[VerifiedStormEventsFile, ...]) -> pd.DataFrame:
    """Read selected checksum-verified details files with source metadata."""

    if not files:
        raise ValueError("At least one verified NOAA details file is required")
    frames: list[pd.DataFrame] = []
    for verified in files:
        if verified.source.dataset != "details":
            raise ValueError(f"Expected a details file, received: {verified.source.dataset}")
        try:
            frame = pd.read_csv(
                verified.path,
                compression="gzip",
                dtype="string",
                keep_default_na=False,
                low_memory=False,
                usecols=list(DETAIL_COLUMNS),
            )
        except (OSError, UnicodeError, ValueError, pd.errors.ParserError) as exc:
            raise NOAAStormEventsError(
                f"Could not read NOAA details file: {verified.path.name}"
            ) from exc
        frame = frame.assign(
            source_filename=verified.source.filename,
            source_data_year=verified.source.data_year,
            source_schema_version=verified.source.schema_version,
            source_created_on=verified.source.created_on.isoformat(),
            source_retrieved_at=verified.manifest_record.get("retrieved_at"),
        )
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _parsed_damage_columns(values: pd.Series, prefix: str) -> pd.DataFrame:
    parsed = [parse_damage_amount(value) for value in values]
    return pd.DataFrame(
        {
            f"{prefix}_dollars": pd.array(
                [item.dollars for item in parsed],
                dtype="Float64",
            ),
            f"{prefix}_status": pd.array(
                [item.status for item in parsed],
                dtype="string",
            ),
            f"{prefix}_suffix": pd.array(
                [item.suffix for item in parsed],
                dtype="string",
            ),
        },
        index=values.index,
    )


def _share(numerator: int, denominator: int) -> float | None:
    if not denominator:
        return None
    return round(numerator / denominator, 6)


def _sum_or_none(values: pd.Series) -> float | None:
    observed = values.dropna()
    if observed.empty:
        return None
    return round(float(observed.sum()), 2)


def _status_counts(values: pd.Series, prefix: str) -> dict[str, int]:
    return {f"{prefix}_{status}_count": int(values.eq(status).sum()) for status in DAMAGE_STATUSES}


def _damage_summary(events: pd.DataFrame) -> dict[str, object]:
    event_count = len(events)
    property_valid = events["damage_property_status"].isin(("parsed", "reported_zero"))
    crop_valid = events["damage_crops_status"].isin(("parsed", "reported_zero"))
    duplicate_mask = events["event_id"].notna() & events["event_id"].duplicated(keep=False)
    invalid_mask = events["damage_property_status"].eq("invalid") | events[
        "damage_crops_status"
    ].eq("invalid")
    missing_mask = events["damage_property_status"].eq("missing") | events[
        "damage_crops_status"
    ].eq("missing")
    positive_mask = events["known_total_damage_dollars"].fillna(0).gt(0)

    duplicate_event_count = int(events.loc[duplicate_mask, "event_id"].nunique())
    complete_count = int(events["is_damage_complete"].sum())
    summary: dict[str, object] = {
        "event_count": event_count,
        "unique_event_count": int(events["event_id"].nunique()),
        "source_file_count": int(events["source_filename"].nunique()),
        "source_filenames": sorted(
            str(value) for value in events["source_filename"].dropna().unique()
        ),
        "source_data_years": sorted(
            int(value) for value in events["source_data_year"].dropna().unique()
        ),
        "source_schema_versions": sorted(
            str(value) for value in events["source_schema_version"].dropna().unique()
        ),
        "missing_event_id_count": int(events["event_id"].isna().sum()),
        "duplicate_event_id_count": duplicate_event_count,
        "duplicate_event_id_record_count": int(duplicate_mask.sum()),
        "source_year_inconsistency_count": int((~events["is_source_year_consistent"]).sum()),
        **_status_counts(events["damage_property_status"], "property"),
        **_status_counts(events["damage_crops_status"], "crops"),
        "valid_property_damage_count": int(property_valid.sum()),
        "valid_property_damage_rate": _share(int(property_valid.sum()), event_count),
        "valid_crop_damage_count": int(crop_valid.sum()),
        "valid_crop_damage_rate": _share(int(crop_valid.sum()), event_count),
        "complete_damage_event_count": complete_count,
        "complete_damage_event_rate": _share(complete_count, event_count),
        "invalid_damage_event_count": int(invalid_mask.sum()),
        "missing_damage_component_event_count": int(missing_mask.sum()),
        "positive_known_damage_event_count": int(positive_mask.sum()),
        "known_property_damage_dollars": _sum_or_none(events["damage_property_dollars"]),
        "known_crop_damage_dollars": _sum_or_none(events["damage_crops_dollars"]),
        "known_total_damage_dollars": _sum_or_none(events["known_total_damage_dollars"]),
    }
    warning_flags: list[str] = []
    if not event_count:
        warning_flags.append("no_events")
    if event_count and not int(property_valid.sum() + crop_valid.sum()):
        warning_flags.append("no_valid_damage_values")
    if int(invalid_mask.sum()):
        warning_flags.append("invalid_damage_values")
    if int(missing_mask.sum()):
        warning_flags.append("missing_damage_values")
    if duplicate_event_count:
        warning_flags.append("duplicate_event_ids")
    if summary["missing_event_id_count"]:
        warning_flags.append("missing_event_ids")
    if summary["source_year_inconsistency_count"]:
        warning_flags.append("source_year_inconsistencies")
    blocking_flags = {"no_events", "no_valid_damage_values"}
    if blocking_flags.intersection(warning_flags):
        publication_status = "blocked"
    elif warning_flags:
        publication_status = "warning"
    else:
        publication_status = "ready"
    summary["publication_status"] = publication_status
    summary["warning_flags"] = warning_flags
    return summary


def _annual_summary(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    years = sorted(int(year) for year in events["source_data_year"].dropna().unique())
    for year in years:
        subset = events.loc[events["source_data_year"].eq(year)]
        summary = _damage_summary(subset)
        rows.append(
            {
                "data_year": year,
                "event_count": summary["event_count"],
                "unique_event_count": summary["unique_event_count"],
                "property_parsed_count": summary["property_parsed_count"],
                "property_reported_zero_count": summary["property_reported_zero_count"],
                "property_missing_count": summary["property_missing_count"],
                "property_invalid_count": summary["property_invalid_count"],
                "crops_parsed_count": summary["crops_parsed_count"],
                "crops_reported_zero_count": summary["crops_reported_zero_count"],
                "crops_missing_count": summary["crops_missing_count"],
                "crops_invalid_count": summary["crops_invalid_count"],
                "complete_damage_event_count": summary["complete_damage_event_count"],
                "known_property_damage_dollars": summary["known_property_damage_dollars"],
                "known_crop_damage_dollars": summary["known_crop_damage_dollars"],
                "known_total_damage_dollars": summary["known_total_damage_dollars"],
            }
        )
    return pd.DataFrame(rows, columns=ANNUAL_SUMMARY_COLUMNS)


def analyze_storm_event_damage(frame: pd.DataFrame) -> StormDamageResult:
    """Parse event damage fields and retain complete missingness diagnostics."""

    missing_columns = sorted(set(DETAIL_COLUMNS) - set(frame.columns))
    if missing_columns:
        raise ValueError(f"NOAA details data are missing fields: {missing_columns}")
    source = frame.copy()
    for column in SOURCE_COLUMNS:
        if column not in source:
            source[column] = pd.NA

    events = pd.DataFrame(
        {
            "episode_id": pd.to_numeric(source["EPISODE_ID"], errors="coerce").astype("Int64"),
            "event_id": pd.to_numeric(source["EVENT_ID"], errors="coerce").astype("Int64"),
            "event_year": pd.to_numeric(source["YEAR"], errors="coerce").astype("Int64"),
            "state": source["STATE"].astype("string").str.strip(),
            "state_fips": source["STATE_FIPS"].astype("string").str.strip(),
            "event_type": source["EVENT_TYPE"].astype("string").str.strip(),
            "cz_type": source["CZ_TYPE"].astype("string").str.strip(),
            "cz_fips": source["CZ_FIPS"].astype("string").str.strip(),
            "cz_name": source["CZ_NAME"].astype("string").str.strip(),
            "damage_property_raw": source["DAMAGE_PROPERTY"].astype("string"),
            "damage_crops_raw": source["DAMAGE_CROPS"].astype("string"),
            "source_filename": source["source_filename"].astype("string"),
            "source_data_year": pd.to_numeric(source["source_data_year"], errors="coerce").astype(
                "Int64"
            ),
            "source_schema_version": source["source_schema_version"].astype("string"),
            "source_created_on": source["source_created_on"].astype("string"),
            "source_retrieved_at": source["source_retrieved_at"].astype("string"),
        }
    )
    events = pd.concat(
        [
            events,
            _parsed_damage_columns(events["damage_property_raw"], "damage_property"),
            _parsed_damage_columns(events["damage_crops_raw"], "damage_crops"),
        ],
        axis=1,
    )
    property_valid = events["damage_property_status"].isin(("parsed", "reported_zero"))
    crop_valid = events["damage_crops_status"].isin(("parsed", "reported_zero"))
    events["known_total_damage_dollars"] = events[
        ["damage_property_dollars", "damage_crops_dollars"]
    ].sum(axis=1, min_count=1)
    events["is_damage_complete"] = property_valid & crop_valid
    events["has_positive_known_damage"] = events["known_total_damage_dollars"].fillna(0).gt(0)
    events["is_source_year_consistent"] = (
        events["event_year"].notna()
        & events["source_data_year"].notna()
        & events["event_year"].eq(events["source_data_year"])
    )
    events = events.sort_values(
        ["source_data_year", "event_id", "source_filename"],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)
    summary = _damage_summary(events)
    return StormDamageResult(
        events=events,
        by_year=_annual_summary(events),
        summary=summary,
    )
