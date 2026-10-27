# Historical county baseline — 2016 vintage

The pilot now has a reproducible import of the official national 2016 SVI county
file, including its ACS 2012–2016 population estimates. This is a historical-vintage
baseline retrieved today, not a certified copy of the data available in 2018.

```bash
python -m recoverylens.historical_context \
  --county-keys data/processed/pilot_losses/candidate_review.csv
```

The county file can contain repeated candidate keys; the command audits each
distinct county once. It writes the national baseline, requested-county audit,
and source manifest under `data/processed/historical_context/`. No event-review
decision or funding record is changed.

## Verified on 27 October 2026

- 3,142 source county rows, with unique five-character keys.
- All 61 distinct pilot counties matched and have positive population and a valid
  overall national SVI rank.
- 3,029 source rows report a population MOE of zero, including all 61 pilot counties.
- CSV and documentation bytes, retrieval times, source URLs, and SHA-256 hashes
  are recorded in the [validation evidence](evidence/historical-context-2026-10-27.json).

Population estimates are baseline values for the pooled ACS period, not annual
population estimates for each disaster year. Published SVI ranks are relative
to their vintage's national universe; this release does not combine vintages or
interpret differences between them as measured changes in vulnerability.

## Uncertainty and availability remain explicit

Raw estimate, MOE, and rank strings are retained. Invalid, nonfinite, negative,
or out-of-range values are withheld analytically. The source's zero MOEs remain
in `population_moe_reported` and receive `published_zero_unreviewed` status.
They are not converted into zero-width analytical intervals. This is a conservative
project policy pending verification of their meaning, not a claim that CDC's
published values are erroneous. Positive published MOEs remain available.

The documentation identifies the ACS source period and variable meanings, but
its revision date does not establish when these exact CSV contents became public.
Archive search results suggest a 2018 deposit exists; its contents and identity
were not verified. No release year is inferred from that search result.
`context_available_year` remains missing and historical-availability approval is false.

A direct Census subject-table lookup returned an HTML "Missing Key" page despite
HTTP 200. It did not yield Census records and was not used as validation evidence.
The CDC bulk download itself required no API key.

Exact county key matches do not prove unchanged historical boundaries. Geography
review and model-context approval remain false. The pilot still needs release
provenance, uncertainty interpretation, boundary review, unresolved event decisions,
comparable monetary scope, and empirical model validation before Milestone 5 closes.

## Official sources

- [2016 national county CSV](https://svi.cdc.gov/Documents/Data/2016/csv/states_counties/SVI_2016_US_county.csv)
- [2016 documentation, revised 19 January 2022](https://svi.cdc.gov/map25/data/docs/SVI2016Documentation_01192022.pdf)
- [CDC/ATSDR download and vintage cautions](https://www.atsdr.cdc.gov/place-health/php/svi/svi-data-documentation-download.html)
