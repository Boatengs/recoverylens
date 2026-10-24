"""Reproducible county context from official ACS bulk files and national SVI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .fema import build_session

ACS_ROOT = "https://www2.census.gov/programs-surveys/acs/summary_file"
SVI_URL = "https://svi.cdc.gov/Documents/Data/2022/csv/states_counties/SVI_2022_US_county.csv"
TABLES = {
    "b01003": {"001": "population"},
    "b19013": {"001": "median_household_income"},
    "b17001": {"001": "poverty_universe", "002": "below_poverty"},
}
RANKS = ["RPL_THEMES", "RPL_THEME1", "RPL_THEME2", "RPL_THEME3", "RPL_THEME4"]


def acquire(url: str, target: Path) -> dict:
    """Download atomically with bounded size and hash the exact source bytes."""
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
        temporary = Path(tmp.name)
        try:
            with build_session().get(url, stream=True, timeout=60) as response:
                response.raise_for_status()
                if "text/html" in response.headers.get("Content-Type", ""):
                    raise ValueError("Source returned HTML instead of data")
                for chunk in response.iter_content(1_048_576):
                    size += len(chunk)
                    if size > 512 * 1024 * 1024:
                        raise ValueError("Source exceeds 512 MiB limit")
                    digest.update(chunk)
                    tmp.write(chunk)
            tmp.flush()
            if size == 0:
                raise ValueError("Empty source file")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return {"url": url, "filename": target.name, "sha256": digest.hexdigest(),
            "bytes": size, "retrieved_at": datetime.now(UTC).isoformat()}


def require_keys(frame: pd.DataFrame, key: str) -> None:
    if frame.empty or frame[key].isna().any() or frame[key].duplicated().any():
        raise ValueError(f"Empty, missing, or duplicate {key}")
    if not frame[key].astype("string").str.fullmatch(r"\d{5}").all():
        raise ValueError(f"Invalid {key}; county keys must have five digits")


def read_acs(path: Path, table: str, year: int) -> pd.DataFrame:
    """Select summary level 050 and retain raw estimates and MOE sentinels."""
    variables = TABLES[table]
    columns = ["GEO_ID"] + [f"{table.upper()}_{kind}{cell}"
                            for cell in variables for kind in ("E", "M")]
    chunks = []
    for chunk in pd.read_csv(path, sep="|", dtype="string", keep_default_na=False,
                             usecols=columns, chunksize=25_000):
        chunks.append(chunk.loc[chunk.GEO_ID.str.fullmatch(r"0500000US\d{5}")])
    raw = pd.concat(chunks, ignore_index=True)
    out = pd.DataFrame({"county_fips": raw.GEO_ID.str[-5:]})
    require_keys(out, "county_fips")
    for cell, name in variables.items():
        for kind, suffix in (("E", "estimate"), ("M", "moe")):
            values = raw[f"{table.upper()}_{kind}{cell}"]
            number = pd.to_numeric(values, errors="coerce")
            valid = number.ge(0) & np.isfinite(number)
            out[f"{name}_{suffix}_raw"] = values
            out[f"{name}_{suffix}"] = number.where(valid)
            out[f"{name}_{suffix}_status"] = np.where(valid, "observed", "unavailable")
            if kind == "M":
                out.loc[number.eq(-555555555), f"{name}_{suffix}_status"] = "controlled"
    return out


def integrate(acs: pd.DataFrame, svi: pd.DataFrame, *, year: int) -> tuple:
    """Outer-join same-vintage keys; never allocate changed counties by name."""
    if year != 2022:
        raise ValueError("This release pins ACS and national SVI to 2022")
    require_keys(acs, "county_fips")
    required = {"FIPS", "LOCATION", *RANKS}
    if not required.issubset(svi):
        raise ValueError(f"SVI is missing fields: {sorted(required - set(svi))}")
    source = svi.copy()
    source["county_fips"] = source.FIPS.astype("string").str.zfill(5)
    require_keys(source, "county_fips")
    selected = source[["county_fips", "LOCATION"]].copy()
    for column in RANKS:
        values = pd.to_numeric(source[column], errors="coerce")
        selected[column + "_raw"] = source[column]
        selected[column] = values.where(values.between(0, 1))
    merged = acs.merge(selected, on="county_fips", how="outer", validate="one_to_one",
                       indicator="geography_status").sort_values("county_fips")
    merged["acs_vintage"] = year
    merged["acs_period_start"] = year - 4
    merged["svi_vintage"] = year
    merged["svi_rank_scope"] = "United States excluding Puerto Rico"
    merged["geography_status"] = merged.geography_status.astype("string").replace(
        {"both": "matched", "left_only": "acs_only", "right_only": "svi_only"})
    merged["context_ready"] = (
        merged.geography_status.eq("matched") & merged.population_estimate.gt(0)
        & merged.RPL_THEMES.notna()
    )
    audit = merged.loc[~merged.context_ready].copy()
    summary = {"acs_county_count": len(acs), "svi_county_count": len(svi),
               "matched_count": int(merged.geography_status.eq("matched").sum()),
               "ready_count": int(merged.context_ready.sum()), "review_count": len(audit),
               "acs_vintage": year, "svi_vintage": year,
               "publication_status": "warning" if len(audit) else "ready",
               "crosswalk_policy": "exact_same_vintage_keys_only; unmatched keys withheld",
               "moe_policy": "raw sentinels retained; unavailable MOE never becomes zero"}
    return merged, audit, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/context"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/context"))
    args = parser.parse_args()
    manifest = []
    acs = None
    for table in TABLES:
        name = f"acsdt5y2022-{table}.dat"
        url = f"{ACS_ROOT}/2022/table-based-SF/data/5YRData/{name}"
        manifest.append(acquire(url, args.raw_dir / name))
        frame = read_acs(args.raw_dir / name, table, 2022)
        if acs is None:
            acs = frame
        else:
            if set(acs.county_fips) != set(frame.county_fips):
                raise ValueError("ACS tables disagree on the county universe")
            acs = acs.merge(frame, on="county_fips", validate="one_to_one")
    manifest.append(acquire(SVI_URL, args.raw_dir / "svi2022.csv"))
    svi = pd.read_csv(args.raw_dir / "svi2022.csv", dtype="string", keep_default_na=False)
    counties, audit, summary = integrate(acs, svi, year=2022)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    counties.to_csv(args.output_dir / "county_context.csv", index=False)
    audit.to_csv(args.output_dir / "geography_review.csv", index=False)
    summary["sources"] = manifest
    (args.output_dir / "manifest.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "sources"}, indent=2))


if __name__ == "__main__":
    main()
