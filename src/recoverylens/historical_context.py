"""2016 baseline county context with explicit availability and uncertainty gates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .context import RANKS, acquire, require_keys

SOURCE_URL = "https://svi.cdc.gov/Documents/Data/2016/csv/states_counties/SVI_2016_US_county.csv"
DOCUMENTATION_URL = "https://svi.cdc.gov/map25/data/docs/SVI2016Documentation_01192022.pdf"


def normalize(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"FIPS", "ST", "LOCATION", "E_TOTPOP", "M_TOTPOP", *RANKS}
    if not required.issubset(frame):
        raise ValueError(f"Missing 2016 county fields: {sorted(required - set(frame))}")
    out = pd.DataFrame({"county_fips": frame.FIPS.astype("string"),
                        "location": frame.LOCATION.astype("string")})
    require_keys(out, "county_fips")
    if not out.county_fips.str[:2].eq(frame.ST.astype("string")).fillna(False).all():
        raise ValueError("State and county identifiers disagree")
    mapping = {"E_TOTPOP": "population_baseline", "M_TOTPOP": "population_moe_reported",
               **{name: name for name in RANKS}}
    for source, name in mapping.items():
        out[name + "_raw"] = frame[source].astype("string")
        number = pd.to_numeric(frame[source], errors="coerce")
        valid = (np.isfinite(number) & number.ge(0)).fillna(False)
        if source in RANKS:
            valid &= number.le(1).fillna(False)
        out[name] = number.where(valid)
    out["population_moe_status"] = "unavailable"
    out.loc[out.population_moe_reported.gt(0), "population_moe_status"] = "published_positive"
    out.loc[out.population_moe_reported.eq(0), "population_moe_status"] = (
        "published_zero_unreviewed")
    # Keep the source's zero, but do not manufacture a zero-width analytical interval.
    out["population_moe"] = out.population_moe_reported.where(out.population_moe_reported.gt(0))
    out["acs_period_start"] = 2012
    out["acs_period_end"] = 2016
    out["svi_vintage"] = 2016
    out["svi_rank_scope"] = "United States excluding Puerto Rico"
    out["context_available_year"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    out["historical_availability_verified"] = False
    out["geography_reviewed"] = False
    out["model_context_approved"] = False
    out["baseline_values_present"] = (
        out.population_baseline.gt(0) & out.RPL_THEMES.notna()).fillna(False)
    return out.sort_values("county_fips").reset_index(drop=True)


def audit_counties(context: pd.DataFrame, requested: pd.DataFrame) -> tuple:
    """Check exact keys without asserting cross-vintage boundary equivalence."""
    require_keys(context, "county_fips")
    require_keys(requested, "county_fips")
    audit = requested[["county_fips"]].merge(context, on="county_fips", how="left",
                                            validate="one_to_one", indicator="key_status")
    audit["key_status"] = audit.key_status.astype("string").replace(
        {"both": "matched", "left_only": "missing_in_2016"})
    for column in ("historical_availability_verified", "geography_reviewed",
                   "model_context_approved", "baseline_values_present"):
        audit[column] = audit[column].astype("boolean").fillna(False)
    summary = {"source_counties": len(context), "requested_counties": len(requested),
               "matched_counties": int(audit.key_status.eq("matched").sum()),
               "missing_counties": int(audit.key_status.eq("missing_in_2016").sum()),
               "matched_with_baseline_values": int(audit.baseline_values_present.eq(True).sum()),
               "published_zero_population_moe_count": int(
                   context.population_moe_reported.eq(0).sum()),
               "requested_zero_population_moe_count": int(
                   audit.population_moe_reported.eq(0).sum()),
               "publication_status": "review_required", "historical_availability_verified": False,
               "model_context_approved": False,
               "geography_policy": "exact keys only; boundary continuity not certified"}
    return audit, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--county-keys", type=Path, required=True,
                        help="CSV with county_fips; repeated candidate keys are deduplicated")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/historical_context"))
    parser.add_argument("--output-dir", type=Path,
                        default=Path("data/processed/historical_context"))
    args = parser.parse_args()
    # Hash and parse the same bytes, so the recorded identity describes the input used.
    import io

    requested_bytes = args.county_keys.read_bytes()
    requested = pd.read_csv(io.BytesIO(requested_bytes), dtype={"county_fips": "string"})
    if "county_fips" not in requested:
        raise ValueError("Requested county file lacks county_fips")
    keys = requested[["county_fips"]].drop_duplicates().reset_index(drop=True)
    require_keys(keys, "county_fips")
    source = acquire(SOURCE_URL, args.raw_dir / "svi2016.csv")
    documentation = acquire(DOCUMENTATION_URL, args.raw_dir / "svi2016-documentation.pdf")
    context = normalize(pd.read_csv(args.raw_dir / "svi2016.csv", dtype="string",
                                    keep_default_na=False))
    audit, report = audit_counties(context, keys)
    report.update(sources=[source, documentation], acs_period=[2012, 2016], svi_vintage=2016,
                  requested_input_sha256=hashlib.sha256(requested_bytes).hexdigest())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    context.to_csv(args.output_dir / "baseline_counties_2016.csv", index=False)
    audit.to_csv(args.output_dir / "pilot_county_audit.csv", index=False)
    (args.output_dir / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "sources"}, indent=2))


if __name__ == "__main__":
    main()
