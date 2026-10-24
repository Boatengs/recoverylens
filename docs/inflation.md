# CPI-adjusted NOAA losses

```bash
python -m recoverylens.inflation --start-year 2005 --end-year 2005 --base-year 2022
```

The command verifies the existing NOAA download manifest before reading detail
files. Download those files first with `recoverylens noaa-download`. The BLS bulk
file is downloaded without an API key, atomically, with retrieval time, byte size,
and SHA-256 recorded. Each run downloads the current BLS revision; retain the raw
file and summary to reproduce a specific revision.

Only published annual-average (`M13`) observations for `CUUR0000SA0` are used:
CPI-U, U.S. city average, all items, not seasonally adjusted. Other series and
monthly records are excluded. No partial-year average, interpolation, or substitute
index is calculated. Duplicate, malformed, nonpositive, or missing annual indexes
fail validation; an unavailable base year stops the run before writing outputs.
Raw index strings and footnote codes remain in the curated CPI table.

Adjusted dollars = nominal dollars × CPI(base year) / CPI(event year).
The event-year convention approximates the price period of the reported loss;
it does not claim month-specific damage valuation. CPI measures consumer prices,
not local construction costs or total economic impact. Funding adjustment needs
its own documented valuation period; this command adjusts NOAA losses only.

## Outputs and gates

- `event_damage_adjusted.csv` preserves every parsed event field and nominal value,
  adding price base, CPI factor, adjusted component/known-total values, and exclusion reasons.
- `damage_adjusted_by_year.csv` sums only eligible adjusted values and reports row
  and complete-component counts. Entirely missing groups remain missing, not zero.
- `cpi_annual.csv` records the selected published indexes and footnotes.
- `summary.json` includes both source manifests, nominal damage diagnostics,
  withheld counts, and publication status.

Duplicate event IDs, missing IDs, source-year disagreement, and unavailable CPI
years are withheld from adjustment and annual totals. Missing or malformed damage
components remain missing. A known total can contain only one reported component;
it is not a complete loss estimate. `inflation_eligible` means the identifier/year
and CPI gates passed, not that damage reporting is complete. Original `blocked`
and `warning` states are never upgraded. An output with no adjusted observations
is blocked.

## Live validation: 24 October 2026

The 2005 NOAA details revision dated 23 March 2026 contained 53,976 unique events,
with no identifier/year/CPI exclusions. Only 3,953 had both damage components;
50,023 had at least one missing component, and one property estimate was invalid.
The run remained `warning`. Published CPI was 195.300 for 2005 and 292.655 for
2022. This validates acquisition and conversion, not national loss completeness.

BLS source SHA-256: `f3c22c8592d9134fa5ab305fa2df6e37dfd2388f10168985fdbc84082deb4ff0`.
NOAA source SHA-256: `d68e3cbfbe5fb79f720eccea372c53585614bab618f3c2a4433e47767f54e55f`.

## Official references

- [BLS bulk data](https://download.bls.gov/pub/time.series/cu/cu.data.1.AllItems)
- [Period codes](https://download.bls.gov/pub/time.series/cu/cu.period)
- [Series identifiers](https://www.bls.gov/cpi/factsheets/cpi-series-ids.htm)
- [Constant-dollar methodology](https://www.bls.gov/cpi/factsheets/purchasing-power-constant-dollars.htm)
