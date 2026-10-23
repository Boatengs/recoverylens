from __future__ import annotations

import csv
import gzip
import io

import pandas as pd
import pytest

from recoverylens.cli import build_parser
from recoverylens.noaa import (
    download_storm_events_files,
    parse_storm_events_filename,
    verified_storm_events_files,
)
from recoverylens.storm_damage import (
    DETAIL_COLUMNS,
    DETAIL_IDENTITY_COLUMNS,
    IMPACT_DETAIL_COLUMNS,
    SOURCE_COLUMNS,
    read_storm_event_details,
)
from recoverylens.storm_impacts import (
    FATALITY_COLUMNS,
    FATALITY_SOURCE_COLUMNS,
    analyze_storm_event_impacts,
    parse_impact_count,
    read_storm_event_fatalities,
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
    def __init__(self, contents: list[bytes]) -> None:
        self.responses = [FakeResponse(content) for content in contents]

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        if not self.responses:
            raise AssertionError("Unexpected HTTP request")
        return self.responses.pop(0)


@pytest.mark.parametrize(
    ("raw", "count", "status"),
    [
        ("2", 2, "parsed"),
        (2.0, 2, "parsed"),
        (" 03 ", 3, "parsed"),
        (0, 0, "reported_zero"),
        ("0", 0, "reported_zero"),
        (None, None, "missing"),
        (pd.NA, None, "missing"),
        ("", None, "missing"),
        ("-1", None, "invalid"),
        ("1.0", None, "invalid"),
        ("1K", None, "invalid"),
        ("not a count", None, "invalid"),
        ("9223372036854775808", None, "invalid"),
    ],
)
def test_parse_impact_count_preserves_count_states(raw, count, status):
    parsed = parse_impact_count(raw)

    assert parsed.count == count
    assert parsed.status == status


def detail_record(
    event_id: object,
    *,
    injuries_direct: object = "0",
    injuries_indirect: object = "0",
    deaths_direct: object = "0",
    deaths_indirect: object = "0",
    event_year: object = 2020,
    source_year: object = 2020,
) -> dict[str, object]:
    return {
        "EPISODE_ID": "10",
        "EVENT_ID": event_id,
        "STATE": "MASSACHUSETTS",
        "STATE_FIPS": "25",
        "YEAR": event_year,
        "EVENT_TYPE": "Flood",
        "CZ_TYPE": "C",
        "CZ_FIPS": "025",
        "CZ_NAME": "SUFFOLK",
        "INJURIES_DIRECT": injuries_direct,
        "INJURIES_INDIRECT": injuries_indirect,
        "DEATHS_DIRECT": deaths_direct,
        "DEATHS_INDIRECT": deaths_indirect,
        "source_filename": f"details-{source_year}.csv.gz",
        "source_data_year": source_year,
        "source_schema_version": "1.0",
        "source_created_on": "2026-03-23",
        "source_retrieved_at": "2026-10-23T15:00:00Z",
    }


def fatality_record(
    fatality_id: object,
    event_id: object,
    fatality_type: object,
    *,
    fatality_year: int = 2020,
    source_year: int = 2020,
    row_number: int = 2,
) -> dict[str, object]:
    return {
        "FAT_YEARMONTH": f"{fatality_year}01",
        "FATALITY_ID": fatality_id,
        "EVENT_ID": event_id,
        "FATALITY_TYPE": fatality_type,
        "source_filename": f"fatalities-{source_year}.csv.gz",
        "source_data_year": source_year,
        "source_schema_version": "1.0",
        "source_created_on": "2026-03-23",
        "source_retrieved_at": "2026-10-23T15:00:00Z",
        "source_row_number": row_number,
    }


def test_impact_analysis_aggregates_counts_and_reconciles_fatalities():
    details = pd.DataFrame(
        [
            detail_record(
                1,
                injuries_direct="2",
                injuries_indirect="1",
                deaths_direct="1",
            ),
            detail_record(2, deaths_indirect="1"),
        ]
    )
    fatalities = pd.DataFrame(
        [
            fatality_record(100, 1, "D", row_number=2),
            fatality_record(101, 2, "i", row_number=3),
        ]
    )

    result = analyze_storm_event_impacts(details, fatalities)

    assert result.events["event_id"].tolist() == [1, 2]
    assert result.events["fatality_reconciliation_status"].tolist() == ["matched", "matched"]
    assert result.summary["publication_status"] == "ready"
    assert result.summary["included_event_count"] == 2
    assert result.summary["known_direct_injuries"] == 2
    assert result.summary["known_indirect_injuries"] == 1
    assert result.summary["known_total_injuries"] == 3
    assert result.summary["known_direct_deaths"] == 1
    assert result.summary["known_indirect_deaths"] == 1
    assert result.summary["known_total_deaths"] == 2
    assert result.summary["roster_direct_death_count"] == 1
    assert result.summary["roster_indirect_death_count"] == 1
    assert result.summary["fatality_roster_coverage_rate"] == 1.0
    assert result.summary["fatality_roster_count_variance"] == 0
    assert result.summary["fatality_reconciliation_rate"] == 1.0
    assert result.unmatched_fatalities.empty
    assert result.by_year.loc[0, "known_total_injuries"] == 3
    assert result.by_year.loc[0, "known_total_deaths"] == 2


def test_impact_analysis_excludes_ambiguous_records_and_reports_mismatch():
    details = pd.DataFrame(
        [
            detail_record(1, injuries_direct="", deaths_direct="1"),
            detail_record(2, deaths_direct="1"),
            detail_record(3),
            detail_record(3),
            detail_record(None),
            detail_record(4, event_year=2021, source_year=2020),
        ]
    )
    fatalities = pd.DataFrame(
        [
            fatality_record(10, 1, "D", row_number=2),
            fatality_record(11, 1, "D", row_number=3),
            fatality_record(11, 1, "D", row_number=4),
            fatality_record(12, 1, "D", row_number=5),
            fatality_record(12, 2, "I", row_number=6),
            fatality_record(13, 3, "D", row_number=7),
            fatality_record(14, 999, "D", row_number=8),
            fatality_record(15, 2, "X", row_number=9),
            fatality_record(16, None, "D", row_number=10),
            fatality_record(None, 2, "D", row_number=11),
            fatality_record(17, 1, "D", fatality_year=2021, row_number=12),
        ]
    )

    result = analyze_storm_event_impacts(details, fatalities)

    assert result.summary["included_event_count"] == 2
    assert result.summary["duplicate_event_id_count"] == 1
    assert result.summary["duplicate_event_id_record_count"] == 2
    assert result.summary["missing_event_id_record_count"] == 1
    assert result.summary["event_source_year_inconsistency_count"] == 1
    assert result.summary["duplicate_fatality_id_count"] == 2
    assert result.summary["conflicting_fatality_id_count"] == 1
    assert result.summary["included_fatality_record_count"] == 1
    assert result.summary["unmatched_fatality_record_count"] == 10
    assert result.summary["fatality_reconciliation_matched_event_count"] == 1
    assert result.summary["fatality_reconciliation_mismatch_event_count"] == 1
    assert result.summary["fatality_roster_coverage_rate"] == 0.5
    assert result.summary["fatality_roster_count_variance"] == -1
    assert result.summary["publication_status"] == "warning"
    assert set(result.unmatched_fatalities["aggregation_status"]) == {
        "ambiguous_event_id",
        "duplicate_fatality_id",
        "invalid_fatality_type",
        "missing_event_id",
        "missing_fatality_id",
        "source_year_inconsistent",
        "unmatched_event_id",
    }
    event_two = result.events.loc[result.events["event_id"].eq(2)].iloc[0]
    assert event_two["fatality_reconciliation_status"] == "mismatch"
    assert event_two["total_death_variance"] == -1


def test_impact_analysis_blocks_empty_inputs_with_stable_outputs():
    detail_columns = [*DETAIL_IDENTITY_COLUMNS, *IMPACT_DETAIL_COLUMNS]
    details = pd.DataFrame(columns=[*detail_columns, *SOURCE_COLUMNS])
    fatalities = pd.DataFrame(columns=[*FATALITY_COLUMNS, *FATALITY_SOURCE_COLUMNS])

    result = analyze_storm_event_impacts(details, fatalities)

    assert result.summary["publication_status"] == "blocked"
    assert result.summary["warning_flags"] == ["no_events"]
    assert result.by_year.columns.tolist()[0] == "data_year"
    assert result.unmatched_fatalities.empty


def csv_gzip(fieldnames: tuple[str, ...], row: dict[str, object]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(fieldnames))
    writer.writeheader()
    writer.writerow({column: row.get(column, "") for column in fieldnames})
    return gzip.compress(output.getvalue().encode("utf-8"))


def test_verified_readers_load_matching_details_and_fatalities(tmp_path):
    details_item = parse_storm_events_filename(
        "StormEvents_details-ftp_v1.0_d2020_c20260323.csv.gz"
    )
    fatalities_item = parse_storm_events_filename(
        "StormEvents_fatalities-ftp_v1.0_d2020_c20260323.csv.gz"
    )
    details_payload = csv_gzip(DETAIL_COLUMNS, detail_record(1, deaths_direct="1"))
    fatalities_payload = csv_gzip(FATALITY_COLUMNS, fatality_record(10, 1, "D"))
    download_storm_events_files(
        [details_item, fatalities_item],
        tmp_path,
        retrieved_at="2026-10-23T15:00:00Z",
        session=FakeSession([details_payload, fatalities_payload]),
    )

    detail_files = verified_storm_events_files(
        tmp_path, dataset="details", start_year=2020, end_year=2020
    )
    fatality_files = verified_storm_events_files(
        tmp_path, dataset="fatalities", start_year=2020, end_year=2020
    )
    details = read_storm_event_details(detail_files)
    fatalities = read_storm_event_fatalities(fatality_files)
    result = analyze_storm_event_impacts(details, fatalities)

    assert fatalities.loc[0, "source_row_number"] == 2
    assert result.summary["known_total_deaths"] == 1
    assert result.summary["fatality_reconciliation_rate"] == 1.0


def test_noaa_impacts_cli_requires_a_bounded_year_range():
    parser = build_parser()
    args = parser.parse_args(
        [
            "noaa-impacts",
            "--start-year",
            "2020",
            "--end-year",
            "2021",
            "--input-dir",
            "raw",
            "--output-dir",
            "processed",
        ]
    )

    assert args.start_year == 2020
    assert args.end_year == 2021
    assert args.input_dir == "raw"
    assert args.output_dir == "processed"
    assert args.handler.__name__ == "noaa_impacts_command"

    with pytest.raises(SystemExit):
        parser.parse_args(["noaa-impacts", "--start-year", "2020"])
