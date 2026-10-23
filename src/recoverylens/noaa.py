"""Version-aware downloads for NOAA/NCEI Storm Events bulk files."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

NOAA_STORM_EVENTS_BASE = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
NOAA_STORM_EVENTS_SCHEMA = urljoin(NOAA_STORM_EVENTS_BASE, "Storm-Data-Bulk-csv-Format.pdf")
SUPPORTED_STORM_DATASETS = ("details", "fatalities", "locations")
MANIFEST_VERSION = "1.0"

_FILENAME_PATTERN = re.compile(
    r"^StormEvents_(?P<dataset>details|fatalities|locations)-ftp_"
    r"v(?P<schema_version>\d+(?:\.\d+)*)_d(?P<data_year>\d{4})_"
    r"c(?P<created_on>\d{8})\.csv\.gz$"
)
_SCHEMA_VERSION_PATTERN = re.compile(r"^\d+(?:\.\d+)*$")


class NOAAStormEventsError(RuntimeError):
    """Raised when NOAA Storm Events discovery or download cannot be verified."""


@dataclass(frozen=True)
class StormEventsFile:
    """One versioned annual file advertised by NOAA/NCEI."""

    dataset: str
    schema_version: str
    data_year: int
    created_on: date
    filename: str
    url: str

    @property
    def version_key(self) -> tuple[int, ...]:
        """Return a numeric key for deterministic schema-version ordering."""

        return tuple(int(part) for part in self.schema_version.split("."))


@dataclass(frozen=True)
class StormEventsDownloadResult:
    """Verified records and counts from one bounded download run."""

    records: tuple[dict[str, object], ...]
    downloaded_count: int
    reused_count: int
    manifest_path: Path


@dataclass(frozen=True)
class VerifiedStormEventsFile:
    """A local NOAA file whose metadata, size, checksum, and archive are valid."""

    source: StormEventsFile
    path: Path
    manifest_record: dict[str, object]


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.hrefs.append(href)


def _build_session() -> requests.Session:
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


def parse_storm_events_filename(
    filename: str,
    *,
    base_url: str = NOAA_STORM_EVENTS_BASE,
) -> StormEventsFile:
    """Parse one official NOAA annual bulk filename into typed metadata."""

    match = _FILENAME_PATTERN.fullmatch(filename)
    if match is None:
        raise ValueError(f"Unsupported NOAA Storm Events filename: {filename}")
    try:
        created_on = date.fromisoformat(
            f"{match['created_on'][:4]}-{match['created_on'][4:6]}-{match['created_on'][6:]}"
        )
    except ValueError as exc:
        raise ValueError(f"Invalid NOAA creation date in filename: {filename}") from exc
    return StormEventsFile(
        dataset=match["dataset"],
        schema_version=match["schema_version"],
        data_year=int(match["data_year"]),
        created_on=created_on,
        filename=filename,
        url=urljoin(base_url, filename),
    )


def catalog_storm_events_files(
    directory_html: str,
    *,
    base_url: str = NOAA_STORM_EVENTS_BASE,
) -> tuple[StormEventsFile, ...]:
    """Extract a deterministic NOAA file catalog from its directory listing."""

    parser = _LinkParser()
    parser.feed(directory_html)
    files: dict[str, StormEventsFile] = {}
    for href in parser.hrefs:
        filename = href.rsplit("/", maxsplit=1)[-1]
        if _FILENAME_PATTERN.fullmatch(filename):
            files[filename] = parse_storm_events_filename(filename, base_url=base_url)
    return tuple(
        sorted(
            files.values(),
            key=lambda item: (
                item.dataset,
                item.data_year,
                item.version_key,
                item.created_on,
                item.filename,
            ),
        )
    )


def fetch_storm_events_catalog(
    *,
    session: requests.Session | None = None,
    timeout: float = 45,
    catalog_url: str = NOAA_STORM_EVENTS_BASE,
) -> tuple[StormEventsFile, ...]:
    """Retrieve and parse the current official NOAA directory listing."""

    client = session or _build_session()
    try:
        response = client.get(catalog_url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise NOAAStormEventsError("NOAA Storm Events catalog request failed") from exc
    files = catalog_storm_events_files(response.text, base_url=catalog_url)
    if not files:
        raise NOAAStormEventsError("NOAA Storm Events catalog contains no supported files")
    return files


def _validate_selection(
    dataset: str,
    start_year: int,
    end_year: int,
    schema_version: str | None,
) -> None:
    if dataset not in SUPPORTED_STORM_DATASETS:
        raise ValueError(f"dataset must be one of: {', '.join(SUPPORTED_STORM_DATASETS)}")
    if not 1950 <= start_year <= 2100 or not 1950 <= end_year <= 2100:
        raise ValueError("NOAA data years must be between 1950 and 2100")
    if start_year > end_year:
        raise ValueError("start_year must be less than or equal to end_year")
    if schema_version is not None and not _SCHEMA_VERSION_PATTERN.fullmatch(schema_version):
        raise ValueError("schema_version must contain only dot-separated integers")


def select_storm_events_files(
    catalog: Sequence[StormEventsFile],
    *,
    dataset: str,
    start_year: int,
    end_year: int,
    schema_version: str | None = None,
) -> tuple[StormEventsFile, ...]:
    """Select one newest available revision for every requested data year."""

    _validate_selection(dataset, start_year, end_year, schema_version)
    selected: list[StormEventsFile] = []
    missing_years: list[int] = []
    for year in range(start_year, end_year + 1):
        candidates = [
            item
            for item in catalog
            if item.dataset == dataset
            and item.data_year == year
            and (schema_version is None or item.schema_version == schema_version)
        ]
        if not candidates:
            missing_years.append(year)
            continue
        selected.append(
            max(
                candidates,
                key=lambda item: (item.version_key, item.created_on, item.filename),
            )
        )
    if missing_years:
        version_text = f" for schema {schema_version}" if schema_version else ""
        missing_text = ", ".join(str(year) for year in missing_years)
        raise NOAAStormEventsError(
            f"NOAA {dataset} files are unavailable{version_text} for years: {missing_text}"
        )
    return tuple(selected)


def _hash_file(path: Path, chunk_size: int = 1_048_576) -> tuple[int, str]:
    digest = hashlib.sha256()
    byte_size = 0
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
            byte_size += len(chunk)
    return byte_size, digest.hexdigest()


def _verify_gzip(path: Path, chunk_size: int = 1_048_576) -> None:
    try:
        with gzip.open(path, "rb") as source:
            while source.read(chunk_size):
                pass
    except (gzip.BadGzipFile, EOFError, OSError) as exc:
        raise NOAAStormEventsError(
            f"Downloaded file is not a valid GZIP archive: {path.name}"
        ) from exc


def _load_manifest(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "manifest_version": MANIFEST_VERSION,
            "source": {
                "catalog_url": NOAA_STORM_EVENTS_BASE,
                "publisher": "NOAA National Centers for Environmental Information",
                "schema_url": NOAA_STORM_EVENTS_SCHEMA,
            },
            "files": [],
        }
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NOAAStormEventsError(f"Could not read NOAA manifest: {path}") from exc
    if manifest.get("manifest_version") != MANIFEST_VERSION or not isinstance(
        manifest.get("files"), list
    ):
        raise NOAAStormEventsError(f"Unsupported NOAA manifest structure: {path}")
    return manifest


def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(manifest, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _source_record(
    item: StormEventsFile,
    *,
    byte_size: int,
    sha256: str,
    retrieved_at: str,
) -> dict[str, object]:
    return {
        "byte_size": byte_size,
        "data_year": item.data_year,
        "dataset": item.dataset,
        "filename": item.filename,
        "noaa_created_on": item.created_on.isoformat(),
        "retrieved_at": retrieved_at,
        "schema_version": item.schema_version,
        "sha256": sha256,
        "source_url": item.url,
    }


def _validate_existing_file(
    item: StormEventsFile,
    target: Path,
    record: dict[str, object] | None,
) -> dict[str, object]:
    if record is None:
        raise NOAAStormEventsError(
            f"Existing NOAA file has no manifest record and cannot be verified: {target.name}"
        )
    expected_metadata = {
        "data_year": item.data_year,
        "dataset": item.dataset,
        "filename": item.filename,
        "noaa_created_on": item.created_on.isoformat(),
        "schema_version": item.schema_version,
        "source_url": item.url,
    }
    if any(record.get(key) != value for key, value in expected_metadata.items()):
        raise NOAAStormEventsError(f"NOAA manifest metadata mismatch for: {target.name}")
    byte_size, sha256 = _hash_file(target)
    if record.get("byte_size") != byte_size or record.get("sha256") != sha256:
        raise NOAAStormEventsError(f"NOAA checksum mismatch for existing file: {target.name}")
    _verify_gzip(target)
    return record


def _download_file(
    item: StormEventsFile,
    target: Path,
    *,
    client: requests.Session,
    timeout: float,
    retrieved_at: str,
) -> dict[str, object]:
    temporary_path: Path | None = None
    response: requests.Response | None = None
    try:
        try:
            response = client.get(item.url, stream=True, timeout=timeout)
            response.raise_for_status()
            digest = hashlib.sha256()
            byte_size = 0
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".part",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                for chunk in response.iter_content(chunk_size=1_048_576):
                    if not chunk:
                        continue
                    temporary.write(chunk)
                    digest.update(chunk)
                    byte_size += len(chunk)
        except requests.RequestException as exc:
            raise NOAAStormEventsError(f"NOAA download failed: {item.url}") from exc
        content_length = response.headers.get("Content-Length")
        try:
            length_mismatch = content_length is not None and int(content_length) != byte_size
        except ValueError as exc:
            raise NOAAStormEventsError(
                f"NOAA returned an invalid content length for: {item.filename}"
            ) from exc
        if length_mismatch:
            raise NOAAStormEventsError(f"NOAA content-length mismatch for: {item.filename}")
        _verify_gzip(temporary_path)
        os.replace(temporary_path, target)
        temporary_path = None
        return _source_record(
            item,
            byte_size=byte_size,
            sha256=digest.hexdigest(),
            retrieved_at=retrieved_at,
        )
    finally:
        if response is not None:
            response.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def download_storm_events_files(
    files: Sequence[StormEventsFile],
    output_dir: Path | str,
    *,
    retrieved_at: str,
    session: requests.Session | None = None,
    timeout: float = 120,
) -> StormEventsDownloadResult:
    """Download selected files atomically and maintain a checksum manifest."""

    if not files:
        raise ValueError("At least one NOAA Storm Events file must be selected")
    if not retrieved_at.strip():
        raise ValueError("retrieved_at must be a nonempty timestamp")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = destination / "manifest.json"
    manifest = _load_manifest(manifest_path)
    records_by_filename = {
        str(record.get("filename")): record
        for record in manifest["files"]
        if isinstance(record, dict) and record.get("filename")
    }
    client = session or _build_session()
    downloaded_count = 0
    reused_count = 0
    selected_records: list[dict[str, object]] = []

    for item in files:
        target = destination / item.filename
        if target.exists() and not target.is_file():
            raise NOAAStormEventsError(f"NOAA output target is not a file: {target}")
        if target.is_file():
            record = _validate_existing_file(item, target, records_by_filename.get(item.filename))
            reused_count += 1
        else:
            record = _download_file(
                item,
                target,
                client=client,
                timeout=timeout,
                retrieved_at=retrieved_at,
            )
            records_by_filename[item.filename] = record
            downloaded_count += 1
            manifest["files"] = sorted(
                records_by_filename.values(),
                key=lambda value: (
                    str(value["dataset"]),
                    int(value["data_year"]),
                    str(value["schema_version"]),
                    str(value["noaa_created_on"]),
                    str(value["filename"]),
                ),
            )
            _write_manifest(manifest_path, manifest)
        selected_records.append(record)

    return StormEventsDownloadResult(
        records=tuple(selected_records),
        downloaded_count=downloaded_count,
        reused_count=reused_count,
        manifest_path=manifest_path,
    )


def verified_storm_events_files(
    input_dir: Path | str,
    *,
    dataset: str,
    start_year: int,
    end_year: int,
    schema_version: str | None = None,
) -> tuple[VerifiedStormEventsFile, ...]:
    """Select and verify local annual files recorded in a NOAA manifest."""

    directory = Path(input_dir)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise NOAAStormEventsError(f"NOAA manifest does not exist: {manifest_path}")
    manifest = _load_manifest(manifest_path)
    catalog: list[StormEventsFile] = []
    records_by_filename: dict[str, dict[str, object]] = {}
    for record in manifest["files"]:
        if not isinstance(record, dict) or not isinstance(record.get("filename"), str):
            raise NOAAStormEventsError(
                f"NOAA manifest contains an invalid file record: {manifest_path}"
            )
        filename = str(record["filename"])
        if filename in records_by_filename:
            raise NOAAStormEventsError(f"NOAA manifest repeats a filename: {filename}")
        try:
            source = parse_storm_events_filename(filename)
        except ValueError as exc:
            raise NOAAStormEventsError(
                f"NOAA manifest contains an invalid filename: {filename}"
            ) from exc
        catalog.append(source)
        records_by_filename[filename] = record

    selected = select_storm_events_files(
        catalog,
        dataset=dataset,
        start_year=start_year,
        end_year=end_year,
        schema_version=schema_version,
    )
    verified: list[VerifiedStormEventsFile] = []
    for source in selected:
        path = directory / source.filename
        if not path.is_file():
            raise NOAAStormEventsError(f"Manifest-listed NOAA file does not exist: {path}")
        record = _validate_existing_file(source, path, records_by_filename[source.filename])
        verified.append(
            VerifiedStormEventsFile(
                source=source,
                path=path,
                manifest_record=record,
            )
        )
    return tuple(verified)
