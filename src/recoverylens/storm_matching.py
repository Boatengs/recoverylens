"""Auditable candidate links between NOAA Storm Events and FEMA declarations."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Integral, Real

import pandas as pd

from .noaa import NOAAStormEventsError, VerifiedStormEventsFile
from .storm_damage import SOURCE_COLUMNS

NOAA_MATCH_COLUMNS = (
    "EPISODE_ID",
    "EVENT_ID",
    "STATE",
    "STATE_FIPS",
    "EVENT_TYPE",
    "CZ_TYPE",
    "CZ_FIPS",
    "CZ_NAME",
    "BEGIN_DATE_TIME",
    "END_DATE_TIME",
)
FEMA_MATCH_COLUMNS = (
    "disasterNumber",
    "state",
    "designatedArea",
    "declarationDate",
    "incidentType",
    "incidentBeginDate",
    "incidentEndDate",
    "fipsStateCode",
    "fipsCountyCode",
)
EVENT_OUTPUT_COLUMNS = (
    "event_record_key",
    "episode_id",
    "event_id",
    "state",
    "state_fips",
    "event_type",
    "cz_type",
    "cz_fips",
    "cz_name",
    "county_fips",
    "event_begin_raw",
    "event_end_raw",
    "event_begin_date",
    "event_end_date",
    "geography_status",
    "window_status",
    "is_source_year_consistent",
    "candidate_count",
    "candidate_disaster_numbers",
    "unique_candidate_disaster_number",
    "match_status",
    "source_filename",
    "source_data_year",
    "source_schema_version",
    "source_created_on",
    "source_retrieved_at",
    "source_row_number",
)
DECLARATION_OUTPUT_COLUMNS = (
    "disaster_number",
    "state",
    "designated_area",
    "declaration_date",
    "incident_type",
    "incident_begin_raw",
    "incident_end_raw",
    "incident_begin_date",
    "incident_end_date",
    "fips_state_code",
    "fips_county_code",
    "county_fips",
    "geography_status",
    "window_status",
    "record_status",
)
CANDIDATE_OUTPUT_COLUMNS = (
    "event_record_key",
    "event_id",
    "episode_id",
    "event_type",
    "event_begin_date",
    "event_end_date",
    "county_fips",
    "cz_name",
    "disaster_number",
    "incident_type",
    "designated_area",
    "declaration_date",
    "incident_begin_date",
    "incident_end_date",
    "date_gap_days",
    "overlap_day_count",
    "candidate_count",
    "match_status",
)
REVIEW_OUTPUT_COLUMNS = ("review_priority", *CANDIDATE_OUTPUT_COLUMNS)
_TWO_DIGIT_EVENT_DATE = re.compile(
    r"^\s*(?P<day>\d{1,2})-(?P<month>[A-Za-z]{3})-(?P<year>\d{2})(?:\s|$)"
)
_MONTH_NUMBERS = {
    name: number
    for number, name in enumerate(
        (
            "",
            "JAN",
            "FEB",
            "MAR",
            "APR",
            "MAY",
            "JUN",
            "JUL",
            "AUG",
            "SEP",
            "OCT",
            "NOV",
            "DEC",
        )
    )
    if name
}


@dataclass(frozen=True)
class StormDeclarationMatchResult:
    """Prepared inputs, candidate links, review queue, and run diagnostics."""

    events: pd.DataFrame
    declarations: pd.DataFrame
    candidates: pd.DataFrame
    review_queue: pd.DataFrame
    summary: dict[str, object]


def _identifier(value: object) -> int | None:
    if value is None or isinstance(value, bool) or bool(pd.isna(value)):
        return None
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        numeric = float(value)
        if numeric.is_integer():
            return int(numeric)
        return None
    normalized = str(value).strip()
    if not normalized or not normalized.isdigit():
        return None
    return int(normalized)


def _normalized_code(values: pd.Series, width: int) -> pd.Series:
    pattern = rf"^(\d{{1,{width}}})(?:\.0+)?$"
    return values.astype("string").str.strip().str.extract(pattern, expand=False).str.zfill(width)


def _raw_text(values: pd.Series) -> pd.Series:
    return values.astype("string")


def _missing_text(values: pd.Series) -> pd.Series:
    return values.isna() | values.astype("string").str.strip().eq("")


def _parse_dates(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce", format="mixed", utc=True)
    return parsed.dt.tz_convert(None).dt.normalize()


def _parse_event_dates(values: pd.Series, source_years: pd.Series) -> pd.Series:
    """Parse NOAA dates, resolving legacy two-digit years from the annual file."""

    parsed = _parse_dates(values)
    resolved = parsed.tolist()
    for index, (value, source_year) in enumerate(zip(values, source_years, strict=True)):
        if (
            value is None
            or bool(pd.isna(value))
            or source_year is None
            or bool(pd.isna(source_year))
        ):
            continue
        match = _TWO_DIGIT_EVENT_DATE.match(str(value))
        if match is None:
            continue
        month = _MONTH_NUMBERS.get(match["month"].upper())
        if month is None:
            resolved[index] = pd.NaT
            continue
        anchor_year = int(source_year)
        two_digit_year = int(match["year"])
        anchor_century = anchor_year // 100 * 100
        candidates = (
            anchor_century - 100 + two_digit_year,
            anchor_century + two_digit_year,
            anchor_century + 100 + two_digit_year,
        )
        resolved_year = min(candidates, key=lambda year: abs(year - anchor_year))
        try:
            resolved[index] = pd.Timestamp(
                year=resolved_year,
                month=month,
                day=int(match["day"]),
            )
        except ValueError:
            resolved[index] = pd.NaT
    return pd.Series(resolved, index=values.index, dtype="datetime64[ns]")


def _window_status(
    begin_raw: pd.Series,
    end_raw: pd.Series,
    begin_date: pd.Series,
    end_date: pd.Series,
    *,
    prefix: str,
) -> pd.Series:
    status = pd.Series("valid", index=begin_raw.index, dtype="string")
    missing_begin = _missing_text(begin_raw)
    missing_end = _missing_text(end_raw)
    status.loc[missing_begin] = f"missing_{prefix}_begin"
    status.loc[~missing_begin & begin_date.isna()] = f"invalid_{prefix}_begin"
    begin_valid = status.eq("valid")
    status.loc[begin_valid & missing_end] = f"missing_{prefix}_end"
    begin_valid = status.eq("valid")
    status.loc[begin_valid & end_date.isna()] = f"invalid_{prefix}_end"
    complete = status.eq("valid")
    status.loc[complete & end_date.lt(begin_date)] = f"{prefix}_end_before_begin"
    return status


def read_storm_event_matching_details(
    files: tuple[VerifiedStormEventsFile, ...],
) -> pd.DataFrame:
    """Read verified NOAA details fields required for candidate-link assessment."""

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
                usecols=list(NOAA_MATCH_COLUMNS),
            )
        except (OSError, UnicodeError, ValueError, pd.errors.ParserError) as exc:
            raise NOAAStormEventsError(
                f"Could not read NOAA matching fields: {verified.path.name}"
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


def prepare_storm_events(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize NOAA event geography and dates without forcing invalid records."""

    required = {*NOAA_MATCH_COLUMNS, *SOURCE_COLUMNS, "source_row_number"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"NOAA matching data are missing fields: {missing}")
    if frame.empty:
        return pd.DataFrame(columns=EVENT_OUTPUT_COLUMNS)

    source = frame.reset_index(drop=True).copy()
    state_fips = _normalized_code(source["STATE_FIPS"], 2)
    county_code = _normalized_code(source["CZ_FIPS"], 3)
    cz_type = source["CZ_TYPE"].astype("string").str.strip().str.upper()
    begin_raw = _raw_text(source["BEGIN_DATE_TIME"])
    end_raw = _raw_text(source["END_DATE_TIME"])
    source_years = pd.Series(
        pd.array([_identifier(value) for value in source["source_data_year"]], dtype="Int64"),
        index=source.index,
    )
    begin_date = _parse_event_dates(begin_raw, source_years)
    end_date = _parse_event_dates(end_raw, source_years)

    events = pd.DataFrame(
        {
            "episode_id": pd.array(
                [_identifier(value) for value in source["EPISODE_ID"]], dtype="Int64"
            ),
            "event_id": pd.array(
                [_identifier(value) for value in source["EVENT_ID"]], dtype="Int64"
            ),
            "state": source["STATE"].astype("string").str.strip(),
            "state_fips": state_fips,
            "event_type": source["EVENT_TYPE"].astype("string").str.strip(),
            "cz_type": cz_type,
            "cz_fips": county_code,
            "cz_name": source["CZ_NAME"].astype("string").str.strip(),
            "event_begin_raw": begin_raw,
            "event_end_raw": end_raw,
            "event_begin_date": begin_date,
            "event_end_date": end_date,
            "source_filename": source["source_filename"].astype("string"),
            "source_data_year": source_years,
            "source_schema_version": source["source_schema_version"].astype("string"),
            "source_created_on": source["source_created_on"].astype("string"),
            "source_retrieved_at": source["source_retrieved_at"].astype("string"),
            "source_row_number": pd.array(
                [_identifier(value) for value in source["source_row_number"]], dtype="Int64"
            ),
        }
    )
    valid_county_code = (
        events["state_fips"].str.fullmatch(r"\d{2}", na=False)
        & events["cz_fips"].str.fullmatch(r"\d{3}", na=False)
        & events["state_fips"].ne("00")
        & events["cz_fips"].ne("000")
    )
    events["county_fips"] = pd.Series(pd.NA, index=events.index, dtype="string")
    county_mask = events["cz_type"].eq("C") & valid_county_code
    events.loc[county_mask, "county_fips"] = (
        events.loc[county_mask, "state_fips"] + events.loc[county_mask, "cz_fips"]
    )

    events["geography_status"] = "unsupported_geography_type"
    events.loc[events["cz_type"].eq("Z"), "geography_status"] = "forecast_zone"
    events.loc[events["cz_type"].eq("M"), "geography_status"] = "marine"
    events.loc[events["cz_type"].isna() | events["cz_type"].eq(""), "geography_status"] = (
        "missing_geography_type"
    )
    county_type = events["cz_type"].eq("C")
    raw_state_missing = _missing_text(source["STATE_FIPS"])
    raw_county_missing = _missing_text(source["CZ_FIPS"])
    events.loc[county_type, "geography_status"] = "invalid_county_code"
    events.loc[county_type & (raw_state_missing | raw_county_missing), "geography_status"] = (
        "missing_county_code"
    )
    events.loc[county_mask, "geography_status"] = "county"
    events["window_status"] = _window_status(
        begin_raw,
        end_raw,
        begin_date,
        end_date,
        prefix="event",
    )
    events["is_source_year_consistent"] = (
        events["event_begin_date"].notna()
        & events["source_data_year"].notna()
        & events["event_begin_date"].dt.year.eq(events["source_data_year"])
    )
    duplicate_event = events["event_id"].notna() & events["event_id"].duplicated(keep=False)
    events["match_status"] = "eligible"
    events.loc[~events["is_source_year_consistent"], "match_status"] = (
        "source_year_inconsistent"
    )
    events.loc[events["window_status"].ne("valid"), "match_status"] = events.loc[
        events["window_status"].ne("valid"), "window_status"
    ]
    events.loc[events["geography_status"].ne("county"), "match_status"] = events.loc[
        events["geography_status"].ne("county"), "geography_status"
    ]
    events.loc[duplicate_event, "match_status"] = "duplicate_event_id"
    events.loc[events["event_id"].isna(), "match_status"] = "missing_event_id"
    events["candidate_count"] = pd.array([0] * len(events), dtype="Int64")
    events["candidate_disaster_numbers"] = pd.Series("", index=events.index, dtype="string")
    events["unique_candidate_disaster_number"] = pd.array(
        [pd.NA] * len(events), dtype="Int64"
    )
    events["event_record_key"] = (
        events["source_filename"].fillna("<unknown>")
        + ":"
        + events["source_row_number"].astype("string").fillna("?")
    )
    return (
        events.loc[:, EVENT_OUTPUT_COLUMNS]
        .sort_values(
            ["source_data_year", "event_id", "source_filename", "source_row_number"],
            kind="mergesort",
            na_position="last",
        )
        .reset_index(drop=True)
    )


def prepare_declaration_windows(
    records: Sequence[Mapping[str, object]] | pd.DataFrame,
) -> pd.DataFrame:
    """Normalize FEMA county incident windows and retain unusable rows for review."""

    source = (
        records.copy()
        if isinstance(records, pd.DataFrame)
        else pd.DataFrame.from_records(records)
    )
    if source.empty:
        return pd.DataFrame(columns=DECLARATION_OUTPUT_COLUMNS)
    missing = sorted(set(FEMA_MATCH_COLUMNS) - set(source.columns))
    if missing:
        raise ValueError(f"FEMA declaration records are missing fields: {missing}")

    state_fips = _normalized_code(source["fipsStateCode"], 2)
    county_code = _normalized_code(source["fipsCountyCode"], 3)
    begin_raw = _raw_text(source["incidentBeginDate"])
    end_raw = _raw_text(source["incidentEndDate"])
    begin_date = _parse_dates(begin_raw)
    end_date = _parse_dates(end_raw)
    declarations = pd.DataFrame(
        {
            "disaster_number": pd.array(
                [_identifier(value) for value in source["disasterNumber"]], dtype="Int64"
            ),
            "state": source["state"].astype("string").str.strip().str.upper(),
            "designated_area": source["designatedArea"].astype("string").str.strip(),
            "declaration_date": _parse_dates(source["declarationDate"]),
            "incident_type": source["incidentType"].astype("string").str.strip(),
            "incident_begin_raw": begin_raw,
            "incident_end_raw": end_raw,
            "incident_begin_date": begin_date,
            "incident_end_date": end_date,
            "fips_state_code": state_fips,
            "fips_county_code": county_code,
        }
    )
    valid_county_code = (
        declarations["fips_state_code"].str.fullmatch(r"\d{2}", na=False)
        & declarations["fips_county_code"].str.fullmatch(r"\d{3}", na=False)
        & declarations["fips_state_code"].ne("00")
        & declarations["fips_county_code"].ne("000")
    )
    declarations["county_fips"] = pd.Series(pd.NA, index=declarations.index, dtype="string")
    declarations.loc[valid_county_code, "county_fips"] = (
        declarations.loc[valid_county_code, "fips_state_code"]
        + declarations.loc[valid_county_code, "fips_county_code"]
    )
    raw_state_missing = _missing_text(source["fipsStateCode"])
    raw_county_missing = _missing_text(source["fipsCountyCode"])
    declarations["geography_status"] = "invalid_county_code"
    declarations.loc[raw_state_missing | raw_county_missing, "geography_status"] = (
        "missing_county_code"
    )
    declarations.loc[
        county_code.eq("000") & state_fips.str.fullmatch(r"\d{2}", na=False),
        "geography_status",
    ] = "non_county_area"
    declarations.loc[valid_county_code, "geography_status"] = "county"
    declarations["window_status"] = _window_status(
        begin_raw,
        end_raw,
        begin_date,
        end_date,
        prefix="incident",
    )
    declarations["record_status"] = "eligible"
    declarations.loc[declarations["window_status"].ne("valid"), "record_status"] = (
        declarations.loc[declarations["window_status"].ne("valid"), "window_status"]
    )
    declarations.loc[declarations["geography_status"].ne("county"), "record_status"] = (
        declarations.loc[declarations["geography_status"].ne("county"), "geography_status"]
    )
    declarations.loc[declarations["disaster_number"].isna(), "record_status"] = (
        "missing_disaster_number"
    )

    exact_columns = [
        column for column in DECLARATION_OUTPUT_COLUMNS if column != "record_status"
    ]
    declarations = declarations.drop_duplicates(subset=exact_columns).copy()
    valid_key = declarations["disaster_number"].notna() & declarations["county_fips"].notna()
    duplicate_key = valid_key & declarations.duplicated(
        subset=["disaster_number", "county_fips"], keep=False
    )
    declarations.loc[duplicate_key, "record_status"] = "duplicate_declaration_area"
    return (
        declarations.loc[:, DECLARATION_OUTPUT_COLUMNS]
        .sort_values(
            ["disaster_number", "county_fips", "designated_area"],
            kind="mergesort",
            na_position="last",
        )
        .reset_index(drop=True)
    )


def _share(numerator: int, denominator: int) -> float | None:
    if not denominator:
        return None
    return round(numerator / denominator, 6)


def _candidate_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=CANDIDATE_OUTPUT_COLUMNS)
    return frame.loc[:, CANDIDATE_OUTPUT_COLUMNS].sort_values(
        ["event_id", "date_gap_days", "disaster_number"],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)


def assess_event_declaration_candidates(
    noaa_details: pd.DataFrame,
    fema_records: Sequence[Mapping[str, object]] | pd.DataFrame,
    *,
    date_buffer_days: int = 0,
    declaration_record_limit_reached: bool = False,
) -> StormDeclarationMatchResult:
    """Assess county/date overlap as reviewable candidates, never confirmed matches."""

    if isinstance(date_buffer_days, bool) or not isinstance(date_buffer_days, Integral):
        raise ValueError("date_buffer_days must be an integer between 0 and 30")
    date_buffer_days = int(date_buffer_days)
    if not 0 <= date_buffer_days <= 30:
        raise ValueError("date_buffer_days must be between 0 and 30")

    events = prepare_storm_events(noaa_details)
    declarations = prepare_declaration_windows(fema_records)
    eligible_events = events.loc[events["match_status"].eq("eligible")].copy()
    eligible_declarations = declarations.loc[declarations["record_status"].eq("eligible")].copy()

    if eligible_events.empty or eligible_declarations.empty:
        candidates = pd.DataFrame(columns=CANDIDATE_OUTPUT_COLUMNS)
    else:
        joined = eligible_events.merge(
            eligible_declarations,
            on="county_fips",
            how="inner",
            suffixes=("", "_fema"),
        )
        before_gap = (
            joined["incident_begin_date"] - joined["event_end_date"]
        ).dt.days.clip(lower=0)
        after_gap = (
            joined["event_begin_date"] - joined["incident_end_date"]
        ).dt.days.clip(lower=0)
        joined["date_gap_days"] = pd.concat([before_gap, after_gap], axis=1).max(axis=1)
        overlap_start = joined[["event_begin_date", "incident_begin_date"]].max(axis=1)
        overlap_end = joined[["event_end_date", "incident_end_date"]].min(axis=1)
        joined["overlap_day_count"] = (
            (overlap_end - overlap_start).dt.days.add(1).clip(lower=0).astype("Int64")
        )
        joined = joined.loc[joined["date_gap_days"].le(date_buffer_days)].copy()
        joined["date_gap_days"] = joined["date_gap_days"].astype("Int64")
        candidate_counts = joined.groupby("event_record_key")["disaster_number"].transform(
            "nunique"
        )
        joined["candidate_count"] = candidate_counts.astype("Int64")
        joined["match_status"] = "ambiguous_candidates"
        joined.loc[joined["candidate_count"].eq(1), "match_status"] = "unique_candidate"
        candidates = _candidate_columns(joined)

    if not candidates.empty:
        counts = candidates.groupby("event_record_key")["disaster_number"].nunique()
        numbers = candidates.groupby("event_record_key")["disaster_number"].agg(
            lambda values: ";".join(str(int(value)) for value in sorted(values.unique()))
        )
        unique_numbers = counts.loc[counts.eq(1)].index.to_series().map(
            candidates.drop_duplicates("event_record_key").set_index("event_record_key")[
                "disaster_number"
            ]
        )
        events["candidate_count"] = events["event_record_key"].map(counts).fillna(0).astype("Int64")
        events["candidate_disaster_numbers"] = (
            events["event_record_key"].map(numbers).fillna("").astype("string")
        )
        events["unique_candidate_disaster_number"] = pd.array(
            events["event_record_key"].map(unique_numbers), dtype="Int64"
        )
    eligible = events["match_status"].eq("eligible")
    events.loc[eligible & events["candidate_count"].eq(0), "match_status"] = "no_candidate"
    events.loc[eligible & events["candidate_count"].eq(1), "match_status"] = "unique_candidate"
    events.loc[eligible & events["candidate_count"].gt(1), "match_status"] = (
        "ambiguous_candidates"
    )
    if not candidates.empty:
        candidate_status = events.set_index("event_record_key")["match_status"]
        candidates["match_status"] = candidates["event_record_key"].map(candidate_status)
        candidates["candidate_count"] = candidates["event_record_key"].map(
            events.set_index("event_record_key")["candidate_count"]
        ).astype("Int64")
        candidates = _candidate_columns(candidates)

    if candidates.empty:
        review_queue = pd.DataFrame(columns=REVIEW_OUTPUT_COLUMNS)
    else:
        review_queue = candidates.copy()
        review_queue.insert(
            0,
            "review_priority",
            review_queue["match_status"].map(
                {"ambiguous_candidates": "high", "unique_candidate": "standard"}
            ),
        )
        review_queue = review_queue.sort_values(
            ["review_priority", "event_id", "date_gap_days", "disaster_number"],
            ascending=[True, True, True, True],
            kind="mergesort",
        ).reset_index(drop=True)

    status_counts = events["match_status"].value_counts()
    event_count = len(events)
    eligible_event_count = int(
        status_counts.get("unique_candidate", 0)
        + status_counts.get("ambiguous_candidates", 0)
        + status_counts.get("no_candidate", 0)
    )
    candidate_event_count = int(
        status_counts.get("unique_candidate", 0)
        + status_counts.get("ambiguous_candidates", 0)
    )
    unique_count = int(status_counts.get("unique_candidate", 0))
    ambiguous_count = int(status_counts.get("ambiguous_candidates", 0))
    no_candidate_count = int(status_counts.get("no_candidate", 0))
    unmatchable_count = event_count - eligible_event_count
    ineligible_declaration_count = int(declarations["record_status"].ne("eligible").sum())
    summary: dict[str, object] = {
        "assessment_rule": "county_and_date_overlap_candidates_only",
        "confirmed_match_count": 0,
        "date_buffer_days": date_buffer_days,
        "source_event_record_count": event_count,
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
        "unique_event_id_count": int(events["event_id"].nunique()),
        "eligible_event_count": eligible_event_count,
        "unmatchable_event_count": unmatchable_count,
        "candidate_event_count": candidate_event_count,
        "candidate_event_rate": _share(candidate_event_count, eligible_event_count),
        "unique_candidate_event_count": unique_count,
        "unique_candidate_rate": _share(unique_count, eligible_event_count),
        "ambiguous_candidate_event_count": ambiguous_count,
        "ambiguity_rate": _share(ambiguous_count, candidate_event_count),
        "no_candidate_event_count": no_candidate_count,
        "no_candidate_rate": _share(no_candidate_count, eligible_event_count),
        "candidate_link_count": len(candidates),
        "candidate_disaster_count": int(candidates["disaster_number"].nunique()),
        "source_declaration_record_count": len(declarations),
        "eligible_declaration_area_count": int(
            declarations["record_status"].eq("eligible").sum()
        ),
        "ineligible_declaration_area_count": ineligible_declaration_count,
        "declaration_record_limit_reached": bool(declaration_record_limit_reached),
        "event_status_counts": {
            str(key): int(value) for key, value in sorted(status_counts.items())
        },
        "declaration_status_counts": {
            str(key): int(value)
            for key, value in sorted(declarations["record_status"].value_counts().items())
        },
    }
    warning_flags: list[str] = []
    if not event_count:
        warning_flags.append("no_events")
    elif not eligible_event_count:
        warning_flags.append("no_eligible_events")
    if not len(declarations):
        warning_flags.append("no_declaration_records")
    elif not int(declarations["record_status"].eq("eligible").sum()):
        warning_flags.append("no_eligible_declaration_areas")
    if unmatchable_count:
        warning_flags.append("unmatchable_events")
    if ineligible_declaration_count:
        warning_flags.append("ineligible_declaration_areas")
    if no_candidate_count:
        warning_flags.append("events_without_candidates")
    if ambiguous_count:
        warning_flags.append("ambiguous_candidates")
    if candidate_event_count:
        warning_flags.append("candidate_links_require_review")
    if date_buffer_days:
        warning_flags.append("date_buffer_applied")
    if declaration_record_limit_reached:
        warning_flags.append("declaration_record_limit_reached")
    blocking_flags = {"no_events", "no_eligible_events"}
    if blocking_flags.intersection(warning_flags):
        publication_status = "blocked"
    elif warning_flags:
        publication_status = "warning"
    else:
        publication_status = "ready"
    summary["publication_status"] = publication_status
    summary["warning_flags"] = warning_flags

    return StormDeclarationMatchResult(
        events=events.loc[:, EVENT_OUTPUT_COLUMNS],
        declarations=declarations,
        candidates=candidates,
        review_queue=review_queue,
        summary=summary,
    )
