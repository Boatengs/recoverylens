import pandas as pd
import pytest

from recoverylens.boundary_audit import audit


def note(code="019", date="01-01-2017", submitted="04-11-2017"):
    return {"State": "NC-37", "Entity Name": "Example", "Entity Code": code,
            "Type of Change": "County Boundary Correction", "Effective Date": date,
            "Description of Change": "Exchanged territory", "Date Submitted": submitted}


def keys(*values):
    return pd.DataFrame({"county_fips": pd.Series(values, dtype="string")})


def test_screen_retains_late_corrections_and_multiple_notes_without_certification():
    notes = pd.DataFrame([note(), note(date="01-01-2020", submitted="08-04-2023"),
                          note("01972"), note("037", "01-01-2015")])
    counties, evidence, report = audit(notes, keys("37019", "37037"))
    assert counties.county_note_count.tolist() == [2, 0]
    assert not counties.geography_reviewed.any()
    assert counties.boundary_screen_status.tolist() == [
        "county_note_requires_review", "no_county_note_found_not_certified"]
    assert "08-04-2023" in evidence["Date Submitted"].tolist()
    assert report["pilot_counties_with_notes"] == 1


@pytest.mark.parametrize("field,value", [("State", "SC-45"), ("Entity Code", "19"),
                                         ("Effective Date", "unknown")])
def test_invalid_source_fails(field, value):
    row = note()
    row[field] = value
    with pytest.raises(ValueError):
        audit(pd.DataFrame([row]), keys("37019"))


@pytest.mark.parametrize("requested", [keys("45051"), keys("37019", "37019"), keys()])
def test_invalid_requested_keys_fail(requested):
    with pytest.raises(ValueError):
        audit(pd.DataFrame([note()]), requested)


def test_missing_schema_fails():
    with pytest.raises(ValueError, match="Missing"):
        audit(pd.DataFrame([note()]).drop(columns="Type of Change"), keys("37019"))


def test_no_county_notes_does_not_certify_continuity():
    counties, evidence, report = audit(pd.DataFrame([note("01972")]), keys("37019"))
    assert evidence.empty
    assert counties.county_note_count.tolist() == [0]
    assert report["geography_reviewed"] is False
