# Official data source registry

RecoveryLens gives priority to reproducible, machine-readable government sources. Retrieval dates and source metadata will be written alongside generated datasets in later milestones.

## FEMA OpenFEMA

### Disaster Declarations Summaries v2

- Canonical documentation: https://www.fema.gov/openfema-data-page/disaster-declarations-summaries-v2
- API endpoint: `https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries`
- Grain: one designated geographic area per disaster declaration
- Key fields: disaster number, declaration and incident dates, incident type, state, designated area, state FIPS, county FIPS, and declared assistance programs
- Intended use: county disaster exposure and eligibility context
- Important limitation: county detail is unavailable before 1964; historical records originate in an operational system and can contain human error.

### Public Assistance Funded Projects Details v2

- Canonical documentation: https://www.fema.gov/openfema-data-page/public-assistance-funded-projects-details-v2
- API endpoint: `https://www.fema.gov/api/open/v2/PublicAssistanceFundedProjectsDetails`
- Grain: funded Public Assistance project worksheet
- Timing fields: disaster declaration date, first obligation date, and last obligation date
- Category field: FEMA damage category code, mapped to Categories A–G and management-cost Category Z
- Intended use: obligated federal share, project categories, recipients, and disaster-level funding
- Important limitation: unobligated projects are excluded. FEMA states that these values can differ from official federal financial reporting and should not be used as official federal reports.

## NOAA National Centers for Environmental Information

### Storm Events Database

- Search: https://www.ncei.noaa.gov/access/storm-events-database/
- Bulk files: https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/
- Bulk-file README: https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/README
- Bulk CSV schema: https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/Storm-Data-Bulk-csv-Format.pdf
- Grain: recorded storm event or episode
- Intended use: event type, property damage, crop damage, injuries, fatalities, and geographic exposure
- Revision rule: filenames retain the table, CSV schema version, data year, and NOAA creation date. RecoveryLens resolves the newest revision within the requested schema—or the newest available schema when no version is pinned—and records the exact filename and checksum.
- Damage rule: compact property and crop estimates are parsed with their magnitude suffix while the raw string and parse status remain visible. Blank or malformed values are not converted to zero.
- Important limitation: reporting practices and event coverage vary over time. Dollar strings require documented parsing, and loss values are not comprehensive estimates of total economic impact.

## U.S. Census Bureau

### American Community Survey 5-year

- Documentation: https://www.census.gov/programs-surveys/acs/data/data-via-api.html
- API root: `https://api.census.gov/data/2024/acs/acs5`
- Grain: selected Census geography and estimate
- Intended use: population denominators, income, poverty, age, disability, housing, internet access, and rural context
- Important limitation: estimates include sampling uncertainty. RecoveryLens will retain margins of error where used and avoid treating estimates as exact counts.

## CDC/ATSDR

### Social Vulnerability Index 2022

- Download and documentation: https://www.atsdr.cdc.gov/place-health/php/svi/svi-data-documentation-download.html
- Grain: county or census tract
- Intended use: published overall and theme-level vulnerability ranks
- Important limitation: SVI is contextual, not a measure of individual vulnerability or proof of inequity. Version year must remain visible because it does not represent real-time conditions.

## Join standard

County data will use the five-character Census county FIPS code (`state FIPS + county FIPS`) as the canonical geographic key. Records without a valid county FIPS will remain in a documented unmatched table and will not be silently assigned by name.
