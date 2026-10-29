"""Auditable annual CPI-U adjustment of verified NOAA event losses."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .context import acquire
from .modeling import adjust_dollars
from .noaa import verified_storm_events_files
from .storm_damage import analyze_storm_event_damage, read_storm_event_details

CPI_URL = "https://download.bls.gov/pub/time.series/cu/cu.data.1.AllItems"
SERIES = "CUUR0000SA0"
AMOUNTS = ["damage_property_dollars", "damage_crops_dollars", "known_total_damage_dollars"]
SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "reference" / "cpi_u_annual_m13.tsv"
SNAPSHOT_RETRIEVED = "2026-10-29"


def read_cpi(path: Path) -> pd.DataFrame:
    """Select published M13 annual averages, never partial-year monthly means."""
    raw = pd.read_csv(path, sep="\t", dtype="string", keep_default_na=False)
    raw.columns = raw.columns.str.strip()
    required = {"series_id", "year", "period", "value", "footnote_codes"}
    if not required.issubset(raw):
        raise ValueError("BLS file is missing required fields")
    raw = raw.apply(lambda column: column.str.strip())
    selected = raw.loc[raw.series_id.eq(SERIES) & raw.period.eq("M13")].copy()
    selected["year"] = pd.to_numeric(selected.year, errors="coerce")
    selected["cpi"] = pd.to_numeric(selected.value, errors="coerce")
    if (selected.empty or selected.year.isna().any() or selected.year.duplicated().any()
            or not selected.year.mod(1).eq(0).all() or selected.cpi.isna().any()
            or not selected.cpi.gt(0).all() or not np.isfinite(selected.cpi).all()):
        raise ValueError("Invalid, empty, or duplicate annual CPI observations")
    selected["source_url"] = CPI_URL
    return selected[["year", "cpi", "series_id", "period", "value", "footnote_codes",
                     "source_url"]].sort_values("year").reset_index(drop=True)


def load_cpi(cpi_dir: Path, snapshot: Path = SNAPSHOT) -> tuple[pd.DataFrame, dict]:
    """Download the current BLS file; fall back to the committed annual extract.

    BLS refuses some automated hosts, including GitHub-hosted runners. The extract
    holds only the published M13 rows of the same series, copied from the BLS file,
    so a fallback run uses published values and says so in its source record.
    """
    target = cpi_dir / "cu.data.1.AllItems"
    try:
        source = acquire(CPI_URL, target)
        source["mode"] = "live"
        return read_cpi(target), source
    except Exception as error:  # any download failure uses the committed extract
        if not snapshot.exists():
            raise
        data = snapshot.read_bytes()
        source = {"url": CPI_URL, "mode": "committed_snapshot",
                  "filename": snapshot.name, "sha256": hashlib.sha256(data).hexdigest(),
                  "bytes": len(data), "retrieved_at": SNAPSHOT_RETRIEVED,
                  "live_download_error": f"{type(error).__name__}: {error}"[:300]}
        return read_cpi(snapshot), source


def adjust_events(events: pd.DataFrame, cpi: pd.DataFrame, base_year: int) -> tuple:
    """Retain all rows; exclude duplicate IDs, invalid years, and missing CPI."""
    out = events.copy()
    conversion = adjust_dollars(out.known_total_damage_dollars, out.event_year, cpi, base_year)
    flags = pd.DataFrame({
        "missing_event_id": out.event_id.isna(),
        "duplicate_event_id": out.event_id.duplicated(keep=False),
        "source_year_inconsistent": ~out.is_source_year_consistent.fillna(False),
        "cpi_year_unavailable": conversion.cpi_factor.isna(),
    })
    out["inflation_exclusion_reasons"] = pd.Series(
        [";".join(flags.columns[row]) for row in flags.to_numpy(dtype=bool)],
        index=out.index, dtype="string")
    eligible = ~flags.any(axis=1)
    out["inflation_eligible"] = eligible
    out["price_base_year"] = base_year
    out["cpi_series"] = SERIES
    out["cpi_factor"] = conversion.cpi_factor.where(eligible)
    for amount in AMOUNTS:
        out[amount + "_adjusted"] = out[amount] * out.cpi_factor
    rows = []
    for year, group in out.groupby("event_year", dropna=False, sort=True):
        row = {"event_year": None if pd.isna(year) else int(year),
               "price_base_year": base_year, "event_count": len(group),
               "eligible_event_count": int(group.inflation_eligible.sum()),
               "complete_adjusted_event_count": int(
                   (group.inflation_eligible & group.is_damage_complete).sum())}
        for amount in AMOUNTS:
            row[amount + "_adjusted"] = group[amount + "_adjusted"].sum(min_count=1)
        rows.append(row)
    columns = ["event_year", "price_base_year", "event_count", "eligible_event_count",
               "complete_adjusted_event_count", *[amount + "_adjusted" for amount in AMOUNTS]]
    return out, pd.DataFrame(rows, columns=columns)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--base-year", type=int, required=True)
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw/noaa/storm-events"))
    parser.add_argument("--cpi-dir", type=Path, default=Path("data/raw/cpi"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/noaa/inflation"))
    args = parser.parse_args()
    verified = verified_storm_events_files(
        args.input_dir, dataset="details", start_year=args.start_year, end_year=args.end_year)
    cpi, source = load_cpi(args.cpi_dir)
    damage = analyze_storm_event_damage(read_storm_event_details(verified))
    events, annual = adjust_events(damage.events, cpi, args.base_year)
    withheld = int((~events.inflation_eligible).sum())
    status = damage.summary["publication_status"]
    if not events.known_total_damage_dollars_adjusted.notna().any():
        status = "blocked"
    elif withheld and status == "ready":
        status = "warning"
    summary = {"publication_status": status, "price_base_year": args.base_year,
               "cpi_series": SERIES, "cpi_source": source,
               "noaa_sources": [item.manifest_record for item in verified],
               "nominal_damage_diagnostics": damage.summary,
               "event_count": len(events), "withheld_event_count": withheld,
               "complete_adjusted_event_count": int(
                   (events.inflation_eligible & events.is_damage_complete).sum()),
               "interpretation": "Known reported losses, not total economic or reconstruction cost"}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    events.to_csv(args.output_dir / "event_damage_adjusted.csv", index=False)
    annual.to_csv(args.output_dir / "damage_adjusted_by_year.csv", index=False)
    cpi.to_csv(args.output_dir / "cpi_annual.csv", index=False)
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("publication_status", "event_count",
                                            "withheld_event_count", "price_base_year")}))


if __name__ == "__main__":
    main()
