from __future__ import annotations

import csv
import gzip
import io

import pandas as pd
import pytest

from recoverylens.cli import build_parser
from recoverylens.noaa import (
    NOAAStormEventsError,
    download_storm_events_files,
    parse_storm_events_filename,
    verified_storm_events_files,
)
from recoverylens.storm_damage import (
    DETAIL_COLUMNS,
    SOURCE_COLUMNS,
    analyze_storm_event_damage,
    parse_damage_amount,
    read_storm_event_details,
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
        self.call_count = 0

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.call_count += 1
        return self.response


@pytest.mark.parametrize(
    ("raw", "dollars", "status", "suffix"),
    [
        ("10.00K", 10_000.0, "parsed", "K"),
        ("15m", 15_000_000.0, "parsed", "M"),
        ("1.25B", 1_250_000_000.0, "parsed", "B"),
        ("42", 42.0, "parsed", None),
        (" .5K ", 500.0, "parsed", "K"),
        ("0.00K", 0.0, "reported_zero", "K"),
        (0, 0.0, "reported_zero", None),
    ],
)
def test_parse_damage_amount_handles_supported_values(raw, dollars, status, suffix):
    parsed = parse_damage_amount(raw)

    assert parsed.dollars == dollars
    assert parsed.status == status
    assert parsed.suffix == suffix


@pytest.mark.parametrize(
    ("raw", "status"),
    [
        (None, "missing"),
        (pd.NA, "missing"),
        ("", "missing"),
        ("  ", "missing"),
        ("NA", "invalid"),
        ("-1K", "invalid"),
        ("1T", "invalid"),
        ("1,000", "invalid"),
        ("nan", "invalid"),
        ("infinity", "invalid"),
        (float("inf"), "invalid"),
    ],
)
def test_parse_damage_amount_preserves_missing_and_invalid_states(raw, status):
    parsed = parse_damage_amount(raw)

    assert parsed.dollars is None
    assert parsed.status == status


def detail_record(
    event_id: object,
    *,
    property_damage: object,
    crop_damage: object,
    event_year: object = 2020,
    source_year: object = 2020,
) -> dict[str, object]:
    return {
        "EPISODE_ID": 10,
        "EVENT_ID": event_id,
        "STATE": "MASSACHUSETTS",
        "STATE_FIPS": "25",
        "YEAR": event_year,
        "EVENT_TYPE": "Flood",
        "CZ_TYPE": "C",
        "CZ_FIPS": "025",
        "CZ_NAME": "SUFFOLK",
        "DAMAGE_PROPERTY": property_damage,
        "DAMAGE_CROPS": crop_damage,
        "source_filename": f"details-{source_year}.csv.gz",
        "source_data_year": source_year,
        "source_schema_version": "1.0",
        "source_created_on": "2026-03-23",
        "source_retrieved_at": "2026-10-23T15:00:00Z",
    }


def test_damage_analysis_preserves_partial_totals_and_quality_flags():
    frame = pd.DataFrame(
        [
            detail_record(2, property_damage="1K", crop_damage=""),
            detail_record(1, property_damage="0", crop_damage="2M"),
            detail_record(3, property_damage="bad", crop_damage="1K"),
            detail_record(3, property_damage="1K", crop_damage="0"),
            detail_record(
                4,
                property_damage="0",
                crop_damage="0",
                event_year=2020,
                source_year=2021,
            ),
        ]
    )

    result = analyze_storm_event_damage(frame)

    assert result.events["event_id"].tolist() == [1, 2, 3, 3, 4]
    event_two = result.events.loc[result.events["event_id"].eq(2)].iloc[0]
    assert event_two["damage_property_raw"] == "1K"
    assert event_two["damage_crops_status"] == "missing"
    assert event_two["known_total_damage_dollars"] == 1_000.0
    assert not bool(event_two["is_damage_complete"])

    summary = result.summary
    assert summary["event_count"] == 5
    assert summary["unique_event_count"] == 4
    assert summary["source_file_count"] == 2
    assert summary["source_data_years"] == [2020, 2021]
    assert summary["source_schema_versions"] == ["1.0"]
    assert summary["duplicate_event_id_count"] == 1
    assert summary["duplicate_event_id_record_count"] == 2
    assert summary["source_year_inconsistency_count"] == 1
    assert summary["property_parsed_count"] == 2
    assert summary["property_reported_zero_count"] == 2
    assert summary["property_invalid_count"] == 1
    assert summary["crops_parsed_count"] == 2
    assert summary["crops_reported_zero_count"] == 2
    assert summary["crops_missing_count"] == 1
    assert summary["complete_damage_event_count"] == 3
    assert summary["known_property_damage_dollars"] == 2_000.0
    assert summary["known_crop_damage_dollars"] == 2_001_000.0
    assert summary["known_total_damage_dollars"] == 2_003_000.0
    assert summary["publication_status"] == "warning"
    assert summary["warning_flags"] == [
        "invalid_damage_values",
        "missing_damage_values",
        "duplicate_event_ids",
        "source_year_inconsistencies",
    ]
    assert result.by_year["data_year"].tolist() == [2020, 2021]


def test_damage_analysis_blocks_empty_or_unusable_inputs():
    empty = pd.DataFrame(columns=[*DETAIL_COLUMNS, *SOURCE_COLUMNS])
    empty_result = analyze_storm_event_damage(empty)
    assert empty_result.summary["publication_status"] == "blocked"
    assert empty_result.summary["warning_flags"] == ["no_events"]
    assert empty_result.by_year.columns.tolist() == [
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
    ]

    unusable = pd.DataFrame([detail_record(1, property_damage="unknown", crop_damage="bad")])
    unusable_result = analyze_storm_event_damage(unusable)
    assert unusable_result.summary["publication_status"] == "blocked"
    assert "no_valid_damage_values" in unusable_result.summary["warning_flags"]

    with pytest.raises(ValueError, match="missing fields"):
        analyze_storm_event_damage(pd.DataFrame({"EVENT_ID": [1]}))


def details_gzip(row: dict[str, object]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(DETAIL_COLUMNS))
    writer.writeheader()
    writer.writerow({column: row.get(column, "") for column in DETAIL_COLUMNS})
    return gzip.compress(output.getvalue().encode("utf-8"))


def test_details_reader_requires_and_reads_manifest_verified_files(tmp_path):
    item = parse_storm_events_filename("StormEvents_details-ftp_v1.0_d2020_c20260323.csv.gz")
    payload = details_gzip(detail_record(11, property_damage="2.5K", crop_damage="0"))
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
    frame = read_storm_event_details(verified)
    result = analyze_storm_event_damage(frame)

    assert len(verified) == 1
    assert frame.loc[0, "source_filename"] == item.filename
    assert result.summary["publication_status"] == "ready"
    assert result.summary["known_total_damage_dollars"] == 2_500.0

    (tmp_path / item.filename).write_bytes(b"corrupt")
    with pytest.raises(NOAAStormEventsError, match="checksum mismatch"):
        verified_storm_events_files(
            tmp_path,
            dataset="details",
            start_year=2020,
            end_year=2020,
        )


def test_noaa_damage_cli_is_bounded_and_uses_manifest_directory():
    parser = build_parser()
    args = parser.parse_args(
        [
            "noaa-damage",
            "--start-year",
            "2020",
            "--end-year",
            "2021",
            "--schema-version",
            "1.0",
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
    assert args.handler.__name__ == "noaa_damage_command"

    with pytest.raises(SystemExit):
        parser.parse_args(["noaa-damage", "--start-year", "2020"])
