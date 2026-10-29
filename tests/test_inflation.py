from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from recoverylens.inflation import CPI_URL, SERIES, adjust_events, main, read_cpi


def cpi_file(path, rows=None):
    path.write_text("series_id\tyear\tperiod\tvalue\tfootnote_codes\n" + (
        rows if rows is not None else
        f"{SERIES}\t2005\tM13\t100\t\n{SERIES}\t2022\tM13\t150\t\n"
        f"{SERIES}\t2026\tM01\t200\t\nCUSR0000SA0\t2022\tM13\t999\t\n"))
    return path


def events():
    return pd.DataFrame({
        "event_id": [1, 2, 3, 3, 4, 5, 6],
        "event_year": [2005, 2005, 2005, 2005, 2005, 1900, 2005],
        "is_source_year_consistent": [True, True, True, True, False, True, True],
        "is_damage_complete": [True, False, True, True, True, True, True],
        "damage_property_dollars": [100, np.nan, 100, 100, 100, 100, 0],
        "damage_crops_dollars": [20, np.nan, 0, 0, 0, 0, 0],
        "known_total_damage_dollars": [120, np.nan, 100, 100, 100, 100, 0],
    })


def test_published_annual_series_only(tmp_path):
    cpi = read_cpi(cpi_file(tmp_path / "cpi"))
    assert cpi.year.tolist() == [2005, 2022]
    assert cpi.cpi.tolist() == [100, 150]
    assert cpi.source_url.eq(CPI_URL).all()


@pytest.mark.parametrize("rows", [
    "", f"{SERIES}\t2005\tM13\t0\t\n", f"{SERIES}\t2005\tM13\tbad\t\n",
    f"{SERIES}\t2005.5\tM13\t100\t\n", f"{SERIES}\t\tM13\t100\t\n",
    f"{SERIES}\t2005\tM13\t100\t\n{SERIES}\t2005\tM13\t101\t\n",
])
def test_bad_annual_indexes_fail(tmp_path, rows):
    with pytest.raises(ValueError, match="annual CPI"):
        read_cpi(cpi_file(tmp_path / "cpi", rows))


def test_adjustment_keeps_nominal_missingness_and_excludes_bad_events(tmp_path):
    cpi = read_cpi(cpi_file(tmp_path / "cpi"))
    original = events()
    result, annual = adjust_events(original, cpi, 2022)
    pd.testing.assert_frame_equal(result[original.columns], original)
    assert result.known_total_damage_dollars_adjusted.iloc[0] == 180
    assert result.known_total_damage_dollars_adjusted.iloc[1:6].isna().all()
    assert result.known_total_damage_dollars_adjusted.iloc[6] == 0
    assert result.inflation_eligible.tolist() == [True, True, False, False, False, False, True]
    assert annual.loc[annual.event_year.eq(2005),
                      "known_total_damage_dollars_adjusted"].iloc[0] == 180
    assert pd.isna(annual.loc[annual.event_year.eq(1900),
                             "known_total_damage_dollars_adjusted"].iloc[0])
    with pytest.raises(ValueError, match="base year"):
        adjust_events(original, cpi, 2026)


@pytest.mark.parametrize("empty", [False, True])
def test_cli_preserves_blocked_status_and_provenance(tmp_path, monkeypatch, empty):
    monkeypatch.setattr("sys.argv", ["inflation", "--start-year", "2005", "--end-year",
                                    "2005", "--base-year", "2022", "--cpi-dir", str(tmp_path),
                                    "--output-dir", str(tmp_path / "output")])
    monkeypatch.setattr("recoverylens.inflation.verified_storm_events_files",
                        lambda *a, **k: [SimpleNamespace(manifest_record={"sha256": "noaa"})])
    monkeypatch.setattr("recoverylens.inflation.read_storm_event_details", lambda x: None)
    monkeypatch.setattr("recoverylens.inflation.analyze_storm_event_damage",
                        lambda x: SimpleNamespace(events=events().iloc[:0] if empty else events(),
                                                  summary={
                            "publication_status": "blocked"}))

    def acquire(url, path):
        cpi_file(path)
        return {"sha256": "cpi", "url": url}

    monkeypatch.setattr("recoverylens.inflation.acquire", acquire)
    main()
    output = tmp_path / "output"
    report = json.loads((output / "summary.json").read_text())
    assert report["publication_status"] == "blocked"
    assert report["noaa_sources"] == [{"sha256": "noaa"}]
    assert report["withheld_event_count"] == (0 if empty else 4)
    assert len(pd.read_csv(output / "event_damage_adjusted.csv")) == (0 if empty else 7)
    assert "event_year" in pd.read_csv(output / "damage_adjusted_by_year.csv")


def test_load_cpi_falls_back_to_committed_snapshot(tmp_path, monkeypatch):
    from recoverylens import inflation

    def refused(url, target):
        raise ConnectionError("403 Forbidden")

    monkeypatch.setattr(inflation, "acquire", refused)
    snapshot = cpi_file(tmp_path / "snapshot.tsv")
    cpi, source = inflation.load_cpi(tmp_path / "cpi", snapshot)
    assert source["mode"] == "committed_snapshot"
    assert "403" in source["live_download_error"]
    assert list(cpi.year) == [2005, 2022]


def test_load_cpi_raises_without_snapshot(tmp_path, monkeypatch):
    from recoverylens import inflation

    def refused(url, target):
        raise ConnectionError("403 Forbidden")

    monkeypatch.setattr(inflation, "acquire", refused)
    with pytest.raises(ConnectionError):
        inflation.load_cpi(tmp_path / "cpi", tmp_path / "missing.tsv")


def test_committed_snapshot_is_valid_annual_cpi():
    from recoverylens.inflation import SNAPSHOT

    cpi = read_cpi(SNAPSHOT)
    assert cpi.year.is_monotonic_increasing and {2018, 2019, 2020, 2022} <= set(cpi.year)
    assert cpi.set_index("year").cpi[2022] == pytest.approx(292.655)
