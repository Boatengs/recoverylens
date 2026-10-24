from __future__ import annotations

import pandas as pd
import pytest

from recoverylens.fema import (
    Query,
    aggregate_county_declarations,
    aggregate_county_pa_projects,
    declaration_filter,
    declaration_matching_filter,
    iter_records,
    pa_project_filter,
    prepare_county_declarations,
    prepare_pa_projects,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        return FakeResponse(next(self.pages))


def test_iter_records_paginates_and_respects_limit():
    session = FakeSession(
        [
            {"DisasterDeclarationsSummaries": [{"id": 1}, {"id": 2}]},
            {"DisasterDeclarationsSummaries": [{"id": 3}, {"id": 4}]},
        ]
    )
    query = Query(dataset="declarations", page_size=2, max_records=3)

    assert [row["id"] for row in iter_records(query, session=session)] == [1, 2, 3]
    assert session.calls[1][1]["$skip"] == 2
    assert session.calls[1][1]["$top"] == 1


def test_declaration_filter_validates_inputs():
    assert declaration_filter(state="ma", start_year=2020) == (
        "declarationType eq 'DR' and state eq 'MA' "
        "and declarationDate ge '2020-01-01T00:00:00.000Z'"
    )
    with pytest.raises(ValueError):
        declaration_filter(state="Massachusetts")


def test_declaration_matching_filter_bounds_incident_windows():
    assert declaration_matching_filter(
        state="ma",
        start_year=2020,
        end_year=2021,
        date_buffer_days=2,
    ) == (
        "declarationType eq 'DR' and state eq 'MA' and "
        "incidentBeginDate le '2022-01-02T23:59:59.999Z' and "
        "(incidentEndDate ge '2019-12-30T00:00:00.000Z' or incidentEndDate eq null)"
    )
    with pytest.raises(ValueError):
        declaration_matching_filter(start_year=2021, end_year=2020)
    with pytest.raises(ValueError):
        declaration_matching_filter(start_year=2020, end_year=2020, date_buffer_days=-1)


def test_prepare_and_aggregate_county_declarations():
    records = [
        {
            "disasterNumber": 100,
            "state": "MA",
            "designatedArea": "Suffolk (County)",
            "declarationDate": "2020-01-01T00:00:00Z",
            "incidentType": "Severe Storm",
            "fipsStateCode": "25",
            "fipsCountyCode": "025",
        },
        {
            "disasterNumber": 100,
            "state": "MA",
            "designatedArea": "Suffolk (County)",
            "declarationDate": "2020-01-01T00:00:00Z",
            "incidentType": "Severe Storm",
            "fipsStateCode": 25,
            "fipsCountyCode": 25,
        },
        {
            "disasterNumber": 101,
            "state": "MA",
            "designatedArea": "Statewide",
            "declarationDate": "2021-02-03T00:00:00Z",
            "incidentType": "Snowstorm",
            "fipsStateCode": "25",
            "fipsCountyCode": "000",
        },
    ]

    prepared = prepare_county_declarations(records)
    assert prepared["county_fips"].tolist() == ["25025"]
    aggregated = aggregate_county_declarations(prepared)
    assert aggregated.loc[0, "declaration_count"] == 1
    assert aggregated.loc[0, "state"] == "MA"


def test_pa_project_filter_validates_inputs():
    assert pa_project_filter(state="ma", start_year=2020, disaster_number=4496) == (
        "stateAbbreviation eq 'MA' and "
        "declarationDate ge '2020-01-01T00:00:00.000Z' and "
        "disasterNumber eq 4496"
    )
    with pytest.raises(ValueError):
        pa_project_filter(state="Massachusetts")
    with pytest.raises(ValueError):
        pa_project_filter(disaster_number=0)
    with pytest.raises(ValueError):
        pa_project_filter(start_year=0)


def test_prepare_and_aggregate_pa_projects_preserves_unmatched_geography():
    records = [
        {
            "disasterNumber": 4496,
            "stateAbbreviation": "MA",
            "county": "Suffolk County",
            "stateNumberCode": "25",
            "countyCode": "25",
            "damageCategoryCode": "B",
            "projectStatus": "Eligible",
            "gmProjectId": 101,
            "projectAmount": "100.50",
            "federalShareObligated": "90.45",
            "totalObligated": "90.45",
            "declarationDate": "2020-03-13T00:00:00Z",
            "firstObligationDate": "2020-04-01T00:00:00Z",
            "lastObligationDate": "2020-04-02T00:00:00Z",
        },
        {
            "disasterNumber": 4496,
            "stateAbbreviation": "MA",
            "county": "Suffolk County",
            "stateNumberCode": 25,
            "countyCode": 25,
            "damageCategoryCode": "E",
            "projectStatus": "Eligible",
            "gmProjectId": 102,
            "projectAmount": 200,
            "federalShareObligated": 180,
            "totalObligated": 180,
            "declarationDate": "2020-03-13T00:00:00Z",
            "firstObligationDate": "2020-05-01T00:00:00Z",
            "lastObligationDate": "2020-05-03T00:00:00Z",
        },
        {
            "disasterNumber": 4496,
            "stateAbbreviation": "MA",
            "county": "Statewide",
            "stateNumberCode": "25",
            "countyCode": "000",
            "damageCategoryCode": "Z",
            "projectStatus": "Eligible",
            "gmProjectId": 103,
            "projectAmount": 500,
            "federalShareObligated": 450,
            "totalObligated": 450,
            "declarationDate": "2020-03-13T00:00:00Z",
            "firstObligationDate": "2020-06-01T00:00:00Z",
            "lastObligationDate": "2020-06-01T00:00:00Z",
        },
    ]

    prepared = prepare_pa_projects(records)
    assert prepared["county_fips"].tolist()[:2] == ["25025", "25025"]
    assert not bool(prepared.loc[2, "is_county_attributed"])
    assert pd.isna(prepared.loc[2, "county_fips"])
    assert prepared.loc[2, "county_attribution_status"] == "statewide"

    aggregated = aggregate_county_pa_projects(prepared)
    assert aggregated.loc[0, "county_fips"] == "25025"
    assert aggregated.loc[0, "project_count"] == 2
    assert aggregated.loc[0, "disaster_count"] == 1
    assert aggregated.loc[0, "project_amount"] == pytest.approx(300.50)
    assert aggregated.loc[0, "federal_share_obligated"] == pytest.approx(270.45)
    assert aggregated.loc[0, "total_obligated"] == pytest.approx(270.45)
