"""Screen NC pilot counties against Census boundary-change notes; never certify continuity."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

import pandas as pd

from .context import acquire, require_keys

SOURCE_URL = "https://www2.census.gov/geo/docs/reference/bndrychange/st37_nc_gcn_2014_2020.txt"


def audit(notes: pd.DataFrame, requested: pd.DataFrame) -> tuple:
    """Screen all county-level entries, retaining corrections and late submissions."""
    required = {"State", "Entity Name", "Entity Code", "Type of Change", "Effective Date",
                "Description of Change", "Date Submitted"}
    if not required.issubset(notes):
        raise ValueError("Missing boundary-note fields")
    require_keys(requested, "county_fips")
    if not requested.county_fips.str.startswith("37").all():
        raise ValueError("This source covers North Carolina only")
    if notes.empty or not notes.State.eq("NC-37").all():
        raise ValueError("Empty notes or unexpected source state")
    codes = notes["Entity Code"].astype("string")
    if not codes.str.fullmatch(r"(?:\d{3}|\d{5})").fillna(False).all():
        raise ValueError("Unexpected entity code format")
    # Three-digit entity codes denote counties; five-digit places/subdivisions
    # must not be mistaken for changes to the surrounding county boundary.
    county = notes.loc[codes.str.len().eq(3)].copy()
    dates = pd.to_datetime(county["Effective Date"], format="%m-%d-%Y", errors="coerce")
    if dates.isna().any():
        raise ValueError("County note has an invalid effective date")
    county = county.loc[dates.between("2016-01-01", "2020-12-31")].copy()
    county["county_fips"] = "37" + county["Entity Code"].astype("string")
    relevant = county.loc[county.county_fips.isin(requested.county_fips)].copy()
    out = requested[["county_fips"]].copy()
    out["county_note_count"] = out.county_fips.map(relevant.groupby("county_fips").size())
    out["county_note_count"] = out.county_note_count.fillna(0).astype(int)
    out["boundary_screen_status"] = "no_county_note_found_not_certified"
    out.loc[out.county_note_count.gt(0), "boundary_screen_status"] = "county_note_requires_review"
    out["geography_reviewed"] = False
    report = {"requested_counties": len(out), "source_note_rows": len(notes),
              "county_note_rows_2016_2020": len(county), "pilot_county_note_rows": len(relevant),
              "pilot_counties_with_notes": int(out.county_note_count.gt(0).sum()),
              "flagged_county_fips": sorted(relevant.county_fips.unique().tolist()),
              "geography_reviewed": False,
              "policy": "Notes are a screen, not a complete boundary crosswalk. Effective and "
                        "submission dates do not establish the first affected Census product."}
    return out, relevant, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--county-keys", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/boundary_audit"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/boundary_audit"))
    args = parser.parse_args()
    raw = args.county_keys.read_bytes()
    requested = pd.read_csv(io.BytesIO(raw), dtype="string")
    requested = requested[["county_fips"]].drop_duplicates()
    source = acquire(SOURCE_URL, args.raw_dir / "nc_notes_2014_2020.txt")
    notes = pd.read_csv(args.raw_dir / source["filename"], sep="|", dtype="string",
                        keep_default_na=False)
    counties, evidence, report = audit(notes, requested)
    report.update(source=source, requested_input_sha256=hashlib.sha256(raw).hexdigest())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    counties.to_csv(args.output_dir / "county_screen.csv", index=False)
    evidence.to_csv(args.output_dir / "pilot_notes.csv", index=False)
    (args.output_dir / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
