"""Small, testable client and transformations for the OpenFEMA API."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
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
    if start_year:
        if not 1953 <= start_year <= 2100:
            raise ValueError("start_year must be between 1953 and 2100")
        clauses.append(f"declarationDate ge '{start_year}-01-01T00:00:00.000Z'")
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
