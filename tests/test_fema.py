from __future__ import annotations

import pytest

from recoverylens.fema import (
    Query,
    aggregate_county_declarations,
    declaration_filter,
    iter_records,
    prepare_county_declarations,
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
