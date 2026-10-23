from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date

import pytest
import requests

from recoverylens.cli import build_parser
from recoverylens.noaa import (
    NOAAStormEventsError,
    catalog_storm_events_files,
    download_storm_events_files,
    fetch_storm_events_catalog,
    parse_storm_events_filename,
    select_storm_events_files,
)


class FakeResponse:
    def __init__(
        self,
        *,
        content: bytes = b"",
        text: str = "",
        status_error: bool = False,
    ) -> None:
        self.content = content
        self.text = text
        self.status_error = status_error
        self.headers = {"Content-Length": str(len(content))} if content else {}

    def raise_for_status(self) -> None:
        if self.status_error:
            raise requests.HTTPError("request failed")

    def iter_content(self, chunk_size: int):
        for offset in range(0, len(self.content), chunk_size):
            yield self.content[offset : offset + chunk_size]

    def close(self) -> None:
        pass


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected HTTP request")
        return self.responses.pop(0)


def compressed_csv(rows: str = "EVENT_ID,DAMAGE_PROPERTY\n1,2K\n") -> bytes:
    return gzip.compress(rows.encode("utf-8"))


def test_parse_storm_events_filename_preserves_version_metadata():
    item = parse_storm_events_filename("StormEvents_details-ftp_v1.0_d2024_c20260728.csv.gz")

    assert item.dataset == "details"
    assert item.schema_version == "1.0"
    assert item.version_key == (1, 0)
    assert item.data_year == 2024
    assert item.created_on == date(2026, 7, 28)
    assert item.url.endswith(item.filename)


@pytest.mark.parametrize(
    "filename",
    [
        "README",
        "StormEvents_unknown-ftp_v1.0_d2024_c20260728.csv.gz",
        "StormEvents_details-ftp_v1.0_d2024_c20260230.csv.gz",
    ],
)
def test_parse_storm_events_filename_rejects_unsupported_names(filename):
    with pytest.raises(ValueError):
        parse_storm_events_filename(filename)


def test_catalog_is_filtered_deduplicated_and_deterministic():
    html = """
    <a href="README">README</a>
    <a href="StormEvents_details-ftp_v1.0_d2024_c20260101.csv.gz">old</a>
    <a href="StormEvents_details-ftp_v1.0_d2024_c20260201.csv.gz">new</a>
    <a href="StormEvents_details-ftp_v1.0_d2024_c20260201.csv.gz">duplicate</a>
    <a href="StormEvents_fatalities-ftp_v1.0_d2023_c20260323.csv.gz">fatalities</a>
    """

    catalog = catalog_storm_events_files(html)

    assert [item.filename for item in catalog] == [
        "StormEvents_details-ftp_v1.0_d2024_c20260101.csv.gz",
        "StormEvents_details-ftp_v1.0_d2024_c20260201.csv.gz",
        "StormEvents_fatalities-ftp_v1.0_d2023_c20260323.csv.gz",
    ]


def test_select_uses_latest_schema_and_revision_or_pinned_schema():
    names = [
        "StormEvents_details-ftp_v1.0_d2023_c20260201.csv.gz",
        "StormEvents_details-ftp_v1.0_d2024_c20260101.csv.gz",
        "StormEvents_details-ftp_v1.0_d2024_c20260201.csv.gz",
        "StormEvents_details-ftp_v2.0_d2024_c20260115.csv.gz",
    ]
    catalog = [parse_storm_events_filename(name) for name in names]

    latest = select_storm_events_files(catalog, dataset="details", start_year=2023, end_year=2024)
    pinned = select_storm_events_files(
        catalog,
        dataset="details",
        start_year=2024,
        end_year=2024,
        schema_version="1.0",
    )

    assert latest[0].created_on == date(2026, 2, 1)
    assert latest[1].schema_version == "2.0"
    assert pinned[0].created_on == date(2026, 2, 1)


@pytest.mark.parametrize(
    ("dataset", "start_year", "end_year", "schema_version"),
    [
        ("unknown", 2020, 2021, None),
        ("details", 1949, 2021, None),
        ("details", 2022, 2021, None),
        ("details", 2020, 2021, "v1.0"),
    ],
)
def test_select_rejects_invalid_bounded_inputs(dataset, start_year, end_year, schema_version):
    with pytest.raises(ValueError):
        select_storm_events_files(
            [],
            dataset=dataset,
            start_year=start_year,
            end_year=end_year,
            schema_version=schema_version,
        )


def test_select_reports_every_missing_year():
    item = parse_storm_events_filename("StormEvents_details-ftp_v1.0_d2020_c20260323.csv.gz")

    with pytest.raises(NOAAStormEventsError, match="2021, 2022"):
        select_storm_events_files([item], dataset="details", start_year=2020, end_year=2022)


def test_fetch_catalog_uses_official_listing_and_rejects_empty_catalog():
    filename = "StormEvents_locations-ftp_v1.0_d2024_c20260728.csv.gz"
    session = FakeSession([FakeResponse(text=f'<a href="{filename}">file</a>')])

    catalog = fetch_storm_events_catalog(session=session)

    assert catalog[0].filename == filename
    assert session.calls[0][1] == {"timeout": 45}

    with pytest.raises(NOAAStormEventsError, match="no supported files"):
        fetch_storm_events_catalog(
            session=FakeSession([FakeResponse(text='<a href="README">README</a>')])
        )


def test_download_writes_verified_file_and_deterministic_manifest(tmp_path):
    item = parse_storm_events_filename("StormEvents_details-ftp_v1.0_d1950_c20260323.csv.gz")
    payload = compressed_csv()
    session = FakeSession([FakeResponse(content=payload)])

    result = download_storm_events_files(
        [item],
        tmp_path,
        retrieved_at="2026-10-23T15:00:00Z",
        session=session,
    )

    target = tmp_path / item.filename
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert target.read_bytes() == payload
    assert result.downloaded_count == 1
    assert result.reused_count == 0
    assert manifest["manifest_version"] == "1.0"
    assert manifest["files"] == [
        {
            "byte_size": len(payload),
            "data_year": 1950,
            "dataset": "details",
            "filename": item.filename,
            "noaa_created_on": "2026-03-23",
            "retrieved_at": "2026-10-23T15:00:00Z",
            "schema_version": "1.0",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "source_url": item.url,
        }
    ]
    assert result.manifest_path.read_text(encoding="utf-8").endswith("\n")

    reused = download_storm_events_files(
        [item],
        tmp_path,
        retrieved_at="2026-10-24T15:00:00Z",
        session=FakeSession([]),
    )
    assert reused.downloaded_count == 0
    assert reused.reused_count == 1
    assert reused.records[0]["retrieved_at"] == "2026-10-23T15:00:00Z"


def test_download_rejects_corruption_and_unverified_existing_files(tmp_path):
    item = parse_storm_events_filename("StormEvents_fatalities-ftp_v1.0_d1950_c20260323.csv.gz")
    payload = compressed_csv("FAT_YEARNUM\n1950\n")
    download_storm_events_files(
        [item],
        tmp_path,
        retrieved_at="2026-10-23T15:00:00Z",
        session=FakeSession([FakeResponse(content=payload)]),
    )
    (tmp_path / item.filename).write_bytes(b"changed")

    with pytest.raises(NOAAStormEventsError, match="checksum mismatch"):
        download_storm_events_files(
            [item],
            tmp_path,
            retrieved_at="2026-10-23T15:00:00Z",
            session=FakeSession([]),
        )

    other_dir = tmp_path / "unverified"
    other_dir.mkdir()
    (other_dir / item.filename).write_bytes(payload)
    with pytest.raises(NOAAStormEventsError, match="no manifest record"):
        download_storm_events_files(
            [item],
            other_dir,
            retrieved_at="2026-10-23T15:00:00Z",
            session=FakeSession([]),
        )


def test_download_failure_is_atomic_and_removes_partial_file(tmp_path):
    item = parse_storm_events_filename("StormEvents_details-ftp_v1.0_d1950_c20260323.csv.gz")

    with pytest.raises(NOAAStormEventsError, match="valid GZIP"):
        download_storm_events_files(
            [item],
            tmp_path,
            retrieved_at="2026-10-23T15:00:00Z",
            session=FakeSession([FakeResponse(content=b"not gzip")]),
        )

    assert not (tmp_path / item.filename).exists()
    assert list(tmp_path.glob("*.part")) == []
    assert not (tmp_path / "manifest.json").exists()


def test_download_rejects_empty_selection_and_http_failure(tmp_path):
    with pytest.raises(ValueError, match="At least one"):
        download_storm_events_files([], tmp_path, retrieved_at="2026-10-23T15:00:00Z")

    item = parse_storm_events_filename("StormEvents_details-ftp_v1.0_d1950_c20260323.csv.gz")
    with pytest.raises(NOAAStormEventsError, match="download failed"):
        download_storm_events_files(
            [item],
            tmp_path,
            retrieved_at="2026-10-23T15:00:00Z",
            session=FakeSession([FakeResponse(status_error=True)]),
        )


def test_noaa_cli_requires_an_explicit_bounded_year_range():
    parser = build_parser()
    args = parser.parse_args(
        [
            "noaa-download",
            "--dataset",
            "fatalities",
            "--start-year",
            "2020",
            "--end-year",
            "2021",
            "--schema-version",
            "1.0",
        ]
    )

    assert args.dataset == "fatalities"
    assert args.start_year == 2020
    assert args.end_year == 2021
    assert args.handler.__name__ == "noaa_download_command"

    with pytest.raises(SystemExit):
        parser.parse_args(["noaa-download", "--start-year", "2020"])
