# County context: ACS and SVI

Run `python -m recoverylens.context` from the installed project environment.
The command downloads official Census table-based summary files and CDC's national
county SVI file; no Census API key is required. The supported release is deliberately
pinned to ACS 2018–2022 and SVI 2022. It writes `county_context.csv`,
`geography_review.csv`, and a source manifest under `data/processed/context/`.

## Variables and uncertainty

| Census table/cell | Variable | Retained uncertainty |
|---|---|---|
| B01003/001 | Total population | Published margin of error or controlled-estimate status |
| B19013/001 | Median household income | Published margin of error and raw sentinel |
| B17001/001 | Population with poverty status determined | Published margin of error |
| B17001/002 | Population below poverty level | Published margin of error |

Every estimate and MOE retains its raw source value. Negative sentinels become
missing analytical values. The MOE code `-555555555` receives `controlled` status:
the estimate is controlled to an independent estimate and a sampling-variability
test is not appropriate. It does not become a zero MOE. Other unsupported values
remain unavailable. No poverty percentage or derived MOE is inferred here.

The Census universe is all exact summary-level `0500000US` county rows in B01003.
The other two ACS tables must have exactly the same county key set. Duplicate keys
fail rather than multiplying rows. Same-vintage SVI is joined one-to-one; five-digit
keys are retained as strings. No population allocation or name-based crosswalk is
performed. Cross-vintage geography conversion is outside this release.

## Live validation, 23 October 2026

- 3,222 ACS counties/municipalities; 3,144 national SVI counties.
- All 3,144 SVI keys match ACS; 78 ACS-only keys are Puerto Rico municipalities.
- Puerto Rico has a separate SVI ranking universe and is withheld from national joins.
- 3,095 ACS population MOEs are controlled estimates and 127 are observed margins.
  One matched county lacks a usable income estimate.
- National context joins are available, but individual fields retain their limitations.

The manifest records full source URL, retrieval time, byte count, and SHA-256 for
each of the four downloads. Raw and processed files remain excluded from Git.

## Official references

- [ACS summary files](https://www.census.gov/programs-surveys/acs/data/summary-file.2022.html)
- [Census annotation meanings](https://www.census.gov/data/developers/data-sets/acs-1year/notes-on-acs-estimate-and-annotation-values.html)
- [CDC download interface](https://svi.cdc.gov/dataDownloads/data-download.html)
- [SVI 2022 documentation](https://svi.cdc.gov/map25/data/docs/SVI2022Documentation_ZCTA.pdf)

SVI percentiles cannot be treated as directly comparable absolute vulnerability
measurements across vintages. ACS five-year estimates describe a pooled period.
