"""Small, testable client and transformations for the OpenFEMA API."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from numbers import Integral
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

OPEN_FEMA_BASE = "https://www.fema.gov/api/open/v2"

DATASETS = {
    "declarations": "DisasterDeclarationsSummaries",
    "pa_projects": "PublicAssistanceFundedProjectsDetails",
}


class OpenFEMAError(RuntimeError):
    """Raised when OpenFEMA returns an unusable response."""


@dataclass(frozen=True)
class Query:
    """Bounded OpenFEMA query parameters."""

    dataset: str
    filter_expression: str | None = None
    select: Sequence[str] | None = None
    order_by: str | None = None
    page_size: int = 1_000
    max_records: int | None = None

    def __post_init__(self) -> None:
        if self.dataset not in DATASETS:
            raise ValueError(f"Unsupported dataset alias: {self.dataset}")
        if not 1 <= self.page_size <= 10_000:
            raise ValueError("page_size must be between 1 and 10,000")
        if self.max_records is not None and self.max_records < 1:
            raise ValueError("max_records must be positive")


def build_session() -> requests.Session:
    """Return a session with conservative retry behavior for public APIs."""

    retry = Retry(
        total=4,
        backoff_factor=0.75,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    session = requests.Session()
    session.headers.update({"User-Agent": "RecoveryLens/0.1 (public-data research)"})
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def _records_from_payload(payload: Mapping[str, Any], dataset_name: str) -> list[dict[str, Any]]:
    records = payload.get(dataset_name)
    if isinstance(records, list):
        return records

    candidates = [
        value
        for key, value in payload.items()
        if key != "metadata" and isinstance(value, list)
    ]
    if len(candidates) == 1:
        return candidates[0]
    raise OpenFEMAError(f"Could not identify records in {dataset_name} response")


def iter_records(
    query: Query,
    *,
    session: requests.Session | None = None,
    timeout: float = 45,
) -> Iterator[dict[str, Any]]:
    """Yield records from a paginated OpenFEMA query.

    Pagination stops on an empty/short page or once ``max_records`` is reached.
    The function yields dictionaries so raw source fields remain inspectable.
    """

    dataset_name = DATASETS[query.dataset]
    client = session or build_session()
    emitted = 0
    skip = 0

    while True:
        remaining = None if query.max_records is None else query.max_records - emitted
        if remaining is not None and remaining <= 0:
            return
        top = query.page_size if remaining is None else min(query.page_size, remaining)
        params: dict[str, str | int] = {"$top": top, "$skip": skip, "$format": "json"}
        if query.filter_expression:
            params["$filter"] = query.filter_expression
        if query.select:
            params["$select"] = ",".join(query.select)
        if query.order_by:
            params["$orderby"] = query.order_by

        response = client.get(f"{OPEN_FEMA_BASE}/{dataset_name}", params=params, timeout=timeout)
        try:
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise OpenFEMAError(f"OpenFEMA request failed at offset {skip}") from exc

        page = _records_from_payload(payload, dataset_name)
        if not page:
            return
        for record in page:
            yield record
            emitted += 1
            if query.max_records is not None and emitted >= query.max_records:
                return
        if len(page) < top:
            return
        skip += len(page)


def declaration_filter(*, state: str | None = None, start_year: int | None = None) -> str:
    """Create a conservative filter for major-disaster declaration records."""

    clauses = ["declarationType eq 'DR'"]
    if state:
        normalized = state.strip().upper()
        if len(normalized) != 2 or not normalized.isalpha():
            raise ValueError("state must be a two-letter postal abbreviation")
        clauses.append(f"state eq '{normalized}'")
    if start_year is not None:
        if not 1953 <= start_year <= 2100:
            raise ValueError("start_year must be between 1953 and 2100")
        clauses.append(f"declarationDate ge '{start_year}-01-01T00:00:00.000Z'")
    return " and ".join(clauses)


def declaration_matching_filter(
    *,
    start_year: int,
    end_year: int,
    state: str | None = None,
    date_buffer_days: int = 0,
    event_start_date: date | None = None,
    event_end_date: date | None = None,
) -> str:
    """Create a bounded major-disaster filter for incident-window assessment."""

    if not 1950 <= start_year <= 2100 or not 1950 <= end_year <= 2100:
        raise ValueError("matching years must be between 1950 and 2100")
    if start_year > end_year:
        raise ValueError("start_year must be less than or equal to end_year")
    if isinstance(date_buffer_days, bool) or not isinstance(date_buffer_days, Integral):
        raise ValueError("date_buffer_days must be an integer between 0 and 30")
    date_buffer_days = int(date_buffer_days)
    if not 0 <= date_buffer_days <= 30:
        raise ValueError("date_buffer_days must be between 0 and 30")

    if (event_start_date is None) != (event_end_date is None):
        raise ValueError("Both event date bounds must be provided together")
    if event_start_date is not None and event_end_date < event_start_date:
        raise ValueError("Event date bounds must be chronological")
    start_date = (event_start_date or date(start_year, 1, 1)) - timedelta(days=date_buffer_days)
    end_date = (event_end_date or date(end_year, 12, 31)) + timedelta(days=date_buffer_days)
    clauses = ["declarationType eq 'DR'"]
    if state:
        normalized = state.strip().upper()
        if len(normalized) != 2 or not normalized.isalpha():
            raise ValueError("state must be a two-letter postal abbreviation")
        clauses.append(f"state eq '{normalized}'")
    clauses.extend(
        [
            f"incidentBeginDate le '{end_date.isoformat()}T23:59:59.999Z'",
            "(incidentEndDate ge "
            f"'{start_date.isoformat()}T00:00:00.000Z' or incidentEndDate eq null)",
        ]
    )
    return " and ".join(clauses)


def pa_project_filter(
    *,
    state: str | None = None,
    start_year: int | None = None,
    disaster_number: int | None = None,
) -> str:
    """Create a validated filter for Public Assistance funded projects."""

    clauses: list[str] = []
    if state:
        normalized = state.strip().upper()
        if len(normalized) != 2 or not normalized.isalpha():
            raise ValueError("state must be a two-letter postal abbreviation")
        clauses.append(f"stateAbbreviation eq '{normalized}'")
    if start_year is not None:
        if not 1953 <= start_year <= 2100:
            raise ValueError("start_year must be between 1953 and 2100")
        clauses.append(f"declarationDate ge '{start_year}-01-01T00:00:00.000Z'")
    if disaster_number is not None:
        if not 1 <= disaster_number <= 99_999:
            raise ValueError("disaster_number must be between 1 and 99,999")
        clauses.append(f"disasterNumber eq {disaster_number}")
    return " and ".join(clauses)


def prepare_county_declarations(records: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    """Normalize declaration records and retain county-identifiable rows."""

    columns = [
        "disasterNumber",
        "state",
        "designatedArea",
        "declarationDate",
        "incidentType",
        "fipsStateCode",
        "fipsCountyCode",
    ]
    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        return pd.DataFrame(columns=[*columns, "county_fips"])

    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"Declaration records are missing required fields: {missing}")

    state_fips = (
        frame["fipsStateCode"].astype("string").str.extract(r"(\d+)", expand=False).str.zfill(2)
    )
    county_fips = (
        frame["fipsCountyCode"].astype("string").str.extract(r"(\d+)", expand=False).str.zfill(3)
    )
    frame = frame.assign(
        fipsStateCode=state_fips,
        fipsCountyCode=county_fips,
        declarationDate=pd.to_datetime(frame["declarationDate"], errors="coerce", utc=True),
    )
    valid = (
        frame["fipsStateCode"].str.fullmatch(r"\d{2}", na=False)
        & frame["fipsCountyCode"].str.fullmatch(r"\d{3}", na=False)
        & frame["fipsCountyCode"].ne("000")
    )
    frame = frame.loc[valid].copy()
    frame["county_fips"] = frame["fipsStateCode"] + frame["fipsCountyCode"]
    return frame[[*columns, "county_fips"]].drop_duplicates(
        subset=["disasterNumber", "county_fips"]
    )


def aggregate_county_declarations(frame: pd.DataFrame) -> pd.DataFrame:
    """Create one row per county with exposure counts and coverage dates."""

    if frame.empty:
        return pd.DataFrame(
            columns=[
                "county_fips",
                "state",
                "declaration_count",
                "first_declaration",
                "latest_declaration",
            ]
        )
    required = {"county_fips", "state", "disasterNumber", "declarationDate"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Prepared declaration data are missing fields: {missing}")
    return (
        frame.groupby(["county_fips", "state"], as_index=False)
        .agg(
            declaration_count=("disasterNumber", "nunique"),
            first_declaration=("declarationDate", "min"),
            latest_declaration=("declarationDate", "max"),
        )
        .sort_values(["declaration_count", "county_fips"], ascending=[False, True])
        .reset_index(drop=True)
    )


def prepare_pa_projects(records: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    """Normalize Public Assistance projects without hiding unmatched geography."""

    columns = [
        "disasterNumber",
        "stateAbbreviation",
        "county",
        "stateNumberCode",
        "countyCode",
        "damageCategoryCode",
        "projectStatus",
        "gmProjectId",
        "projectAmount",
        "federalShareObligated",
        "totalObligated",
        "declarationDate",
        "firstObligationDate",
        "lastObligationDate",
    ]
    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        return pd.DataFrame(
            columns=[
                *columns,
                "county_fips",
                "is_county_attributed",
                "county_attribution_status",
            ]
        )

    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"Public Assistance records are missing required fields: {missing}")

    state_raw = frame["stateNumberCode"].astype("string").str.strip()
    county_raw = frame["countyCode"].astype("string").str.strip()
    state_fips = state_raw.str.extract(r"^(\d+)(?:\.0+)?$", expand=False).str.zfill(2)
    county_fips = county_raw.str.extract(r"^(\d+)(?:\.0+)?$", expand=False).str.zfill(3)
    valid_code = (
        state_fips.str.fullmatch(r"\d{2}", na=False)
        & county_fips.str.fullmatch(r"\d{3}", na=False)
        & state_fips.ne("00")
        & county_fips.ne("000")
    )
    missing_code = state_raw.isna() | state_raw.eq("") | county_raw.isna() | county_raw.eq("")
    county_name = frame["county"].astype("string").str.strip()
    statewide = county_name.str.fullmatch(r"state[\s-]*wide", case=False, na=False)
    multi_county = county_name.str.contains(
        r"\b(?:multiple|multi|various|several)\b.*\b(?:count(?:y|ies)|jurisdictions?)\b",
        case=False,
        regex=True,
        na=False,
    )

    attribution_status = pd.Series("invalid_code", index=frame.index, dtype="string")
    attribution_status.loc[valid_code] = "attributed"
    attribution_status.loc[missing_code] = "missing_code"
    attribution_status.loc[multi_county] = "multi_county"
    attribution_status.loc[statewide] = "statewide"
    is_county_attributed = attribution_status.eq("attributed")

    frame = frame.assign(
        stateNumberCode=state_fips,
        countyCode=county_fips,
        county_fips=(state_fips + county_fips).where(is_county_attributed).astype("string"),
        is_county_attributed=is_county_attributed,
        county_attribution_status=attribution_status,
    )
    for column in ("projectAmount", "federalShareObligated", "totalObligated"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ("declarationDate", "firstObligationDate", "lastObligationDate"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce", utc=True)

    return frame[
        [
            *columns,
            "county_fips",
            "is_county_attributed",
            "county_attribution_status",
        ]
    ]


def _sum_if_present(values: pd.Series) -> float:
    """Sum numeric values while retaining missingness when every value is absent."""

    return values.sum(min_count=1)


def aggregate_county_pa_projects(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate county-attributed Public Assistance projects and obligations."""

    output_columns = [
        "county_fips",
        "stateAbbreviation",
        "project_count",
        "disaster_count",
        "project_amount",
        "federal_share_obligated",
        "total_obligated",
        "first_obligation",
        "latest_obligation",
    ]
    if frame.empty:
        return pd.DataFrame(columns=output_columns)

    required = {
        "county_fips",
        "stateAbbreviation",
        "gmProjectId",
        "disasterNumber",
        "projectAmount",
        "federalShareObligated",
        "totalObligated",
        "firstObligationDate",
        "lastObligationDate",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Prepared Public Assistance data are missing fields: {missing}")

    attributed = frame.loc[frame["county_fips"].notna()].copy()
    if attributed.empty:
        return pd.DataFrame(columns=output_columns)

    aggregated = (
        attributed.groupby(["county_fips", "stateAbbreviation"], as_index=False)
        .agg(
            project_count=("gmProjectId", "nunique"),
            disaster_count=("disasterNumber", "nunique"),
            project_amount=("projectAmount", _sum_if_present),
            federal_share_obligated=("federalShareObligated", _sum_if_present),
            total_obligated=("totalObligated", _sum_if_present),
            first_obligation=("firstObligationDate", "min"),
            latest_obligation=("lastObligationDate", "max"),
        )
        .sort_values(["total_obligated", "county_fips"], ascending=[False, True])
        .reset_index(drop=True)
    )
    money_columns = ["project_amount", "federal_share_obligated", "total_obligated"]
    aggregated[money_columns] = aggregated[money_columns].round(2)
    return aggregated
