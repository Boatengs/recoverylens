# Data Sources

RecoveryLens gives priority to official, machine-readable public data. Every derived dataset should retain its source, retrieval time, version or vintage, transformation context, and known limitations.

## Source registry

| Provider | Dataset | Use | Key caution |
|---|---|---|---|
| FEMA OpenFEMA | [Disaster Declarations Summaries v2](https://www.fema.gov/openfema-data-page/disaster-declarations-summaries-v2) | County disaster exposure and assistance-program eligibility | County detail is unavailable before 1964; operational records can contain human error. |
| FEMA OpenFEMA | [Public Assistance Funded Projects Details v2](https://www.fema.gov/openfema-data-page/public-assistance-funded-projects-details-v2) | Obligations, projects, categories, recipients, and timing | Unobligated projects are excluded; values may differ from official federal financial reports. |
| NOAA/NCEI | [Storm Events Database](https://www.ncei.noaa.gov/access/storm-events-database/) and [bulk files](https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/) | Damage, injuries, fatalities, event type, and geography | Coverage and reporting practices vary over time; reported damage is not total economic impact. |
| U.S. Census Bureau | [American Community Survey 5-year](https://www.census.gov/programs-surveys/acs/data/data-via-api.html) | Population and socioeconomic denominators | Estimates include sampling uncertainty; margins of error must remain visible. |
| CDC/ATSDR | [Social Vulnerability Index](https://www.atsdr.cdc.gov/place-health/php/svi/svi-data-documentation-download.html) | Overall and theme-level vulnerability context | SVI is contextual, not an individual measure or proof of inequity; vintage matters. |

## Provenance policy

For every acquired file or API run, retain as applicable:

- canonical source URL or endpoint;
- retrieval timestamp in UTC;
- filters, selected fields, sort order, and record limit;
- upstream schema version, revision date, or survey vintage;
- compressed byte size and SHA-256 checksum for bulk files; and
- transformation and validation status.

## Join standards

The canonical county key is the five-character Census county FIPS code: two-character state FIPS plus three-character county FIPS.

Records without a valid county key are not assigned by name. They remain in documented unmatched outputs. Cross-source event assessment requires exact county FIPS and intersecting date windows by default. It reports unique, ambiguous, and absent candidates separately and never promotes a candidate to a confirmed match automatically.

## NOAA revision handling

NOAA Storm Events filenames identify the table, CSV schema version, data year, and creation date. RecoveryLens discovers the current directory instead of assuming a static filename. The selected file and checksum are recorded so a later upstream correction cannot silently change an earlier run.

## Data not stored in Git

Raw agency extracts and generated analytical outputs are intentionally excluded from the repository. This keeps the codebase reviewable and requires published results to be reproducible through documented commands.

The version-controlled, field-level registry is canonical: [`docs/data-sources.md`](https://github.com/Boatengs/recoverylens/blob/main/docs/data-sources.md).
