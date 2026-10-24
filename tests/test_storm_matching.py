from __future__ import annotations

import csv
import gzip
import io
import json

import pandas as pd
import pytest

from recoverylens.cli import build_parser
from recoverylens.noaa import (
    download_storm_events_files,
    parse_storm_events_filename,
    verified_storm_events_files,
)
from recoverylens.storm_matching import (
    FEMA_MATCH_COLUMNS,
    NOAA_MATCH_COLUMNS,
    assess_event_declaration_candidates,
    prepare_declaration_windows,
    read_storm_event_matching_details,
)


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.headers = {"Content-Length": str(len(content))}

    def raise_for_status(self) -> None:
        pass

    def iter_content(self, chunk_size: int):
        for offset in range(0, len(self.content), chunk_size):
            yield self.content[offset : offset + chunk_size]

    def close(self) -> None:
        pass


class FakeSession:
    def __init__(self, content: bytes) -> None:
        self.response = FakeResponse(content)

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        return self.response


def event_record(
    event_id: object,
    *,
    begin: object = "08/10/2020 10:00:00",
    end: object = "08/10/2020 11:00:00",
    state_fips: object = "25",
    cz_type: object = "C",
    cz_fips: object = "025",
    source_row_number: int = 2,
) -> dict[str, object]:
    return {
        "EPISODE_ID": 900,
        "EVENT_ID": event_id,
        "STATE": "MASSACHUSETTS",
        "STATE_FIPS": state_fips,
        "EVENT_TYPE": "Flash Flood",
        "CZ_TYPE": cz_type,
        "CZ_FIPS": cz_fips,
        "CZ_NAME": "SUFFOLK",
        "BEGIN_DATE_TIME": begin,
        "END_DATE_TIME": end,
        "source_filename": "details-2020.csv.gz",
        "source_data_year": 2020,
        "source_schema_version": "1.0",
        "source_created_on": "2026-03-23",
        "source_retrieved_at": "2026-10-23T15:00:00Z",
        "source_row_number": source_row_number,
    }


def declaration_record(
    disaster_number: object,
    *,
    begin: object,
    end: object,
    state_fips: object = "25",
    county_fips: object = "025",
    incident_type: str = "Flood",
) -> dict[str, object]:
    return {
        "disasterNumber": disaster_number,
        "state": "MA",
        "designatedArea": "Suffolk (County)",
        "declarationDate": "2020-08-15T00:00:00Z",
        "incidentType": incident_type,
        "incidentBeginDate": begin,
        "incidentEndDate": end,
        "fipsStateCode": state_fips,
        "fipsCountyCode": county_fips,
    }


def test_assessment_distinguishes_unique_ambiguous_and_no_candidates():
    events = pd.DataFrame(
        [
            event_record(1),
            event_record(
                2,
                begin="08/20/2020 10:00:00",
                end="08/20/2020 11:00:00",
                source_row_number=3,
            ),
            event_record(
                3,
                begin="01/10/2020 10:00:00",
                end="01/10/2020 11:00:00",
                cz_fips="017",
                source_row_number=4,
            ),
        ]
    )
    declarations = [
        declaration_record(
            100,
            begin="2020-08-01T00:00:00Z",
            end="2020-08-15T23:59:59Z",
        ),
        declaration_record(
            101,
            begin="2020-08-10T00:00:00Z",
            end="2020-08-12T23:59:59Z",
        ),
        declaration_record(
            102,
            begin="2020-08-20T00:00:00Z",
            end="2020-08-21T23:59:59Z",
        ),
    ]

    result = assess_event_declaration_candidates(events, declarations)
    status = result.events.set_index("event_id")["match_status"].to_dict()

    assert status == {1: "ambiguous_candidates", 2: "unique_candidate", 3: "no_candidate"}
    assert result.candidates["disaster_number"].tolist() == [100, 101, 102]
    assert result.events.set_index("event_id").loc[2, "unique_candidate_disaster_number"] == 102
    assert result.summary["candidate_link_count"] == 3
    assert result.summary["confirmed_match_count"] == 0
    assert result.summary["ambiguous_candidate_event_count"] == 1
    assert result.summary["no_candidate_event_count"] == 1
    assert result.summary["publication_status"] == "warning"
    assert "candidate_links_require_review" in result.summary["warning_flags"]
    assert result.review_queue["review_priority"].tolist() == ["high", "high", "standard"]


def test_date_buffer_is_explicit_and_preserves_nonoverlap():
    events = pd.DataFrame(
        [
            event_record(
                1,
                begin="06/10/2020 00:00:00",
                end="06/10/2020 01:00:00",
            )
        ]
    )
    declarations = [
        declaration_record(
            100,
            begin="2020-06-01T00:00:00Z",
            end="2020-06-09T23:59:59Z",
        )
    ]

    strict = assess_event_declaration_candidates(events, declarations)
    buffered = assess_event_declaration_candidates(events, declarations, date_buffer_days=1)

    assert strict.events.loc[0, "match_status"] == "no_candidate"
    assert buffered.events.loc[0, "match_status"] == "unique_candidate"
    assert buffered.candidates.loc[0, "date_gap_days"] == 1
    assert buffered.candidates.loc[0, "overlap_day_count"] == 0
    assert "date_buffer_applied" in buffered.summary["warning_flags"]
    with pytest.raises(ValueError, match="between 0 and 30"):
        assess_event_declaration_candidates(events, declarations, date_buffer_days=31)


def test_legacy_two_digit_event_dates_use_the_annual_source_year():
    legacy = event_record(
        1,
        begin="08-JAN-53 06:30:00",
        end="08-JAN-53 07:00:00",
    )
    legacy["source_data_year"] = 1953

    result = assess_event_declaration_candidates(pd.DataFrame([legacy]), [])

    assert result.events.loc[0, "event_begin_date"] == pd.Timestamp("1953-01-08")
    assert bool(result.events.loc[0, "is_source_year_consistent"])
    assert result.events.loc[0, "match_status"] == "no_candidate"


def test_unmatchable_event_states_remain_visible():
    events = pd.DataFrame(
        [
            event_record(1, cz_type="Z", source_row_number=2),
            event_record(2, cz_type="M", source_row_number=3),
            event_record(3, cz_fips="", source_row_number=4),
            event_record(
                4,
                begin="not-a-date",
                end="08/10/2020 11:00:00",
                source_row_number=5,
            ),
            event_record(5, source_row_number=6),
            event_record(5, source_row_number=7),
            event_record(None, source_row_number=8),
        ]
    )

    result = assess_event_declaration_candidates(events, [])

    assert result.events["match_status"].tolist() == [
        "forecast_zone",
        "marine",
        "missing_county_code",
        "invalid_event_begin",
        "duplicate_event_id",
        "duplicate_event_id",
        "missing_event_id",
    ]
    assert result.summary["eligible_event_count"] == 0
    assert result.summary["unmatchable_event_count"] == 7
    assert result.summary["publication_status"] == "blocked"
    assert result.candidates.empty


def test_invalid_and_duplicate_declaration_areas_are_excluded():
    records = [
        declaration_record(
            100,
            begin="2020-08-01T00:00:00Z",
            end="2020-08-15T00:00:00Z",
        ),
        declaration_record(
            101,
            begin="2020-08-01T00:00:00Z",
            end="2020-08-15T00:00:00Z",
            county_fips="000",
        ),
        declaration_record(
            102,
            begin="2020-08-20T00:00:00Z",
            end="2020-08-01T00:00:00Z",
        ),
        declaration_record(
            103,
            begin="2020-08-01T00:00:00Z",
            end="2020-08-15T00:00:00Z",
        ),
        declaration_record(
            103,
            begin="2020-08-02T00:00:00Z",
            end="2020-08-16T00:00:00Z",
            incident_type="Severe Storm",
        ),
    ]

    prepared = prepare_declaration_windows(records)
    result = assess_event_declaration_candidates(pd.DataFrame([event_record(1)]), records)

    assert prepared["record_status"].tolist() == [
        "eligible",
        "non_county_area",
        "incident_end_before_begin",
        "duplicate_declaration_area",
        "duplicate_declaration_area",
    ]
    assert result.candidates["disaster_number"].tolist() == [100]
    assert result.summary["ineligible_declaration_area_count"] == 4


def test_empty_assessment_is_blocked_with_stable_schemas():
    empty_events = pd.DataFrame(
        columns=[
            *NOAA_MATCH_COLUMNS,
            "source_row_number",
            "source_filename",
            "source_data_year",
            "source_schema_version",
            "source_created_on",
            "source_retrieved_at",
        ]
    )
    empty_declarations = pd.DataFrame(columns=FEMA_MATCH_COLUMNS)

    result = assess_event_declaration_candidates(empty_events, empty_declarations)

    assert result.summary["publication_status"] == "blocked"
    assert result.summary["warning_flags"] == [
        "no_events",
        "no_declaration_records",
    ]
    assert result.events.empty
    assert result.candidates.empty
    assert result.review_queue.columns[0] == "review_priority"


def test_matching_reader_uses_checksum_verified_details(tmp_path):
    item = parse_storm_events_filename("StormEvents_details-ftp_v1.0_d2020_c20260323.csv.gz")
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(NOAA_MATCH_COLUMNS))
    writer.writeheader()
    writer.writerow(
        {
            column: event_record(11).get(column, "")
            for column in NOAA_MATCH_COLUMNS
        }
    )
    payload = gzip.compress(output.getvalue().encode("utf-8"))
    download_storm_events_files(
        [item],
        tmp_path,
        retrieved_at="2026-10-23T15:00:00Z",
        session=FakeSession(payload),
    )
    verified = verified_storm_events_files(
        tmp_path,
        dataset="details",
        start_year=2020,
        end_year=2020,
    )

    frame = read_storm_event_matching_details(verified)

    assert frame.loc[0, "EVENT_ID"] == "11"
    assert frame.loc[0, "source_filename"] == item.filename
    assert frame.loc[0, "source_row_number"] == 2


def test_noaa_fema_match_cli_is_bounded_and_review_oriented():
    args = build_parser().parse_args(
        [
            "noaa-fema-match",
            "--start-year",
            "2020",
            "--end-year",
            "2021",
            "--date-buffer-days",
            "2",
            "--max-declaration-records",
            "500",
            "--input-dir",
            "raw",
            "--output-dir",
            "processed",
        ]
    )

    assert args.start_year == 2020
    assert args.end_year == 2021
    assert args.date_buffer_days == 2
    assert args.max_declaration_records == 500
    assert args.handler.__name__ == "noaa_fema_match_command"


@pytest.mark.parametrize("buffer_days", [0, 2])
def test_cli_queries_cross_year_event_window(monkeypatch, tmp_path, buffer_days):
    from recoverylens import cli

    events = pd.DataFrame([event_record(
        1, begin="12/31/2020 10:00:00", end="01/02/2021 11:00:00"
    )])
    monkeypatch.setattr(cli, "verified_storm_events_files", lambda *a, **kw: ())
    monkeypatch.setattr(cli, "read_storm_event_matching_details", lambda files: events)

    def fetch(query):
        expected_end = "2021-01-02" if buffer_days == 0 else "2021-01-04"
        expected_start = "2020-12-31" if buffer_days == 0 else "2020-12-29"
        assert f"incidentBeginDate le '{expected_end}T23:59:59.999Z'" in query.filter_expression
        assert f"incidentEndDate ge '{expected_start}T00:00:00.000Z'" in query.filter_expression
        return iter([declaration_record(
            100, begin="2021-01-01T00:00:00Z", end="2021-01-02T00:00:00Z"
        )])

    monkeypatch.setattr(cli, "iter_records", fetch)
    args = build_parser().parse_args([
        "noaa-fema-match", "--start-year", "2020", "--end-year", "2020",
        "--date-buffer-days", str(buffer_days), "--output-dir", str(tmp_path),
    ])
    assert args.handler(args) == 0
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["unique_candidate_event_count"] == 1
