# Methodology

## Unit of analysis

The planned national analytical table has one row per U.S. county or county equivalent. The canonical join key is the five-character county FIPS code.

## Conceptual model

RecoveryLens separates four questions that are often incorrectly collapsed:

1. **Exposure:** How often has a county been included in major-disaster declarations?
2. **Documented harm:** What losses, injuries, and fatalities were recorded?
3. **Community context:** What social and economic constraints may complicate recovery?
4. **Funding alignment:** How does obligated assistance compare with documented need?

These components are displayed individually. A composite score is an optional prioritization aid, not the primary evidence.

## Public Assistance project normalization

RecoveryLens treats each OpenFEMA Public Assistance record as a funded project record. Monetary fields are converted to numeric values and obligation dates are parsed in UTC. County attribution is accepted only when the source provides a valid two-character state FIPS code and a nonzero three-character county FIPS code.

Records without a valid county key remain in the prepared data with an explicit attribution flag. They are excluded from county aggregates but are not discarded, imputed by name, or silently reassigned. A later quality-report step will quantify the affected record counts and obligated dollars.

## Funding reconciliation

Public Assistance totals are independently aggregated from the prepared source records and from the curated project table at two grains: `(state, disaster number)` and state. Reconciliation reports retain record counts, unique project counts, project amounts, federal shares, total obligations, and signed source-to-curated variances.

The project key is `(disaster number, FEMA Grants Manager project ID)`. Exact duplicate keys are collapsed. If records sharing a key disagree on geography, category, status, financial values, or obligation dates, every record in that key group is excluded from curated totals and written to the duplicate diagnostic table. Records missing a project ID remain visible because automatically treating them as duplicates would require an unsupported identity assumption.

Dollar comparisons use a default tolerance equal to the greater of one cent or `1e-9 × the absolute source total`. Count comparisons must be exact. Any material monetary difference, count difference, missing-value mismatch, or excluded conflict produces a visible `variance` status.

These checks validate the internal raw-to-curated transformation. They do not establish equivalence with FEMA's official financial reporting systems.

## County-attribution coverage

County attribution is assigned only when FEMA supplies valid state and nonzero county FIPS components and the county label does not indicate a statewide or multi-county project. The classification order prevents a `Statewide` label from being assigned to a county even when the source also contains a nonzero county code.

Every curated project receives one status: `attributed`, `statewide`, `multi_county`, `missing_code`, or `invalid_code`. Multi-county detection is limited to explicit labels such as “multiple counties” or “various counties”; ambiguous names are not inferred. All non-attributed curated records are written with their normalized source fields to an auditable unmatched extract.

The record-attribution rate uses all curated project records as its denominator. The obligation-attribution rate uses the sum of absolute, nonmissing `totalObligated` values so deobligations cannot cancel positive obligations and inflate coverage. Net obligated dollars and missing obligation counts remain visible separately.

The default publication thresholds are 95% for both record and obligation attribution. Falling below either threshold produces a warning. Missing obligation values also produce a warning, while an empty dataset or an absent dollar denominator blocks publication. These are data-quality gates, not evidence that unmatched funding was distributed incorrectly.

## Run-level data-quality reporting

Every Public Assistance quality-report run records its source request and retrieval timestamp alongside source and curated schemas, row counts, duplicate diagnostics, null rates, financial-field coverage, and county-attribution metrics. Validation checks use three explicit severities: `none`, `warning`, and `error`; these roll up to `passed`, `warning`, or `failed` report states. See [data-quality.md](data-quality.md) for interpretation and review guidance.

## Obligation categories and timing

RecoveryLens maps FEMA Public Assistance work categories A–G to the official emergency- and permanent-work definitions and maps Category Z to management costs. Codes are normalized to uppercase; blank and undocumented codes remain visible as `missing` or `unmapped` rather than being inferred. The category reference follows FEMA's [Public Assistance Program and Policy Guide](https://www.fema.gov/sites/default/files/documents/fema_pa_pappg-5.0-amended.pdf) and [management-cost guidance](https://www.fema.gov/sites/default/files/2020-07/fema_DRRA-1215-management-costs-public-assistance-fact-sheet.pdf).

For each curated project, three intervals are calculated from the source timestamps: declaration to first obligation, declaration to last obligation, and first to last obligation. An interval is reported only when its required dates exist and are chronological. Separate flags preserve first or last obligations before the declaration and last obligations before the first obligation. Category tables report project counts, net and absolute obligated dollars, valid timing counts, and the 25th, 50th, and 75th percentiles where applicable.

The declaration date is not an application or project-submission date. These intervals describe recorded administrative milestones and revisions; they are not direct measures of processing time, agency performance, applicant performance, or community recovery speed. Negative obligations and late adjustments can legitimately change the last-obligation date.

## NOAA Storm Events source revisions

NOAA publishes separate annual GZIP-compressed CSV files for event details, fatalities, and locations. Each filename exposes the CSV schema version, data year, and file creation date. Because NOAA states that current and historical years can receive updates or corrections, RecoveryLens discovers the live directory rather than constructing an assumed filename. For each requested year, it selects the newest creation date within an explicitly pinned schema version; without a pin, it selects the highest available numeric schema version and then its newest revision.

Downloads use a caller-supplied inclusive year range. Each file is written to a temporary path, validated as a complete GZIP archive, and moved into place atomically. The raw-data manifest retains the exact source URL, NOAA creation date, retrieval timestamp, compressed byte size, and SHA-256 checksum. An existing file is reused only when its metadata, size, checksum, and GZIP integrity agree with that manifest.

### Property and crop damage

NOAA documents property and crop damage as estimated values with compact magnitude suffixes, such as `10.00K` and `10.00M`. RecoveryLens accepts nonnegative unsuffixed values and `K`, `M`, or `B` suffixes case-insensitively, converting them to dollars and rounding to cents. Every raw value is retained with one of four statuses: `parsed`, `reported_zero`, `missing`, or `invalid`. Negative values, unknown suffixes, comma-formatted strings, nonnumeric text, and nonfinite representations remain invalid.

`known_total_damage_dollars` sums whichever components are valid, but `is_damage_complete` is true only when both property and crop components are valid. Annual and run-level summaries publish observed-value counts alongside dollars so a partial known total cannot be mistaken for comprehensive loss. Duplicate event IDs and disagreements between an event year and its annual source file are flagged, not automatically resolved. NOAA damage values are reported estimates and do not represent complete economic loss.

### Injuries and fatalities

Direct and indirect injury/death fields are parsed as nonnegative integer counts with `parsed`, `reported_zero`, `missing`, or `invalid` states. Known totals sum valid components, while completeness requires both direct and indirect components. Event rows with missing IDs, duplicate IDs, or source-year inconsistencies remain in diagnostics but are excluded from annual totals rather than resolved through an unsupported choice.

NOAA's fatalities table is used only to audit the details-table death counts. Fatality IDs, event IDs, and direct/indirect type are normalized; duplicate or conflicting fatality IDs and rows that cannot link to one eligible event are excluded from roster counts and written to an unmatched extract. For eligible events, direct and indirect roster counts are compared separately with details counts. The published death total continues to come from the details table, so roster rows are never double-counted.

Two reconciliation measures are required. The event-match rate measures how many comparable event rows agree, while fatality-roster coverage divides linked unique roster rows by known details deaths. They answer different questions: a historical file can match many zero-death events while containing only a small share of the person-level records implied by details totals.

### FEMA–NOAA candidate-link assessment

RecoveryLens does not assume that a NOAA event and a FEMA declaration describe the same causal event merely because they share a place and time. It first limits NOAA rows to county-designated records (`CZ_TYPE = C`) with a valid five-character county FIPS, unique event ID, source-year-consistent begin date, and valid begin/end window. Forecast-zone and marine records remain visible but are not converted to counties. FEMA declaration areas likewise require a valid disaster number, nonzero county FIPS, and chronological incident begin/end dates; duplicated disaster–county keys with conflicting metadata are excluded rather than resolved arbitrarily.

A candidate is generated when an eligible NOAA event and eligible FEMA major-disaster declaration share the exact county FIPS and their inclusive calendar-date windows overlap. NOAA documents event timestamps as usually local time, while FEMA supplies incident date fields; the assessment therefore does not claim time-of-day precision across the sources. The CLI accepts an optional zero-to-30-day buffer; buffered links retain both the actual overlap-day count and the nonoverlap gap, and the summary raises a `date_buffer_applied` warning. Event type and FEMA incident type are retained for review but are not used as an undocumented synonym map.

Every NOAA row receives one state: `unique_candidate`, `ambiguous_candidates`, `no_candidate`, or a specific unmatchable condition such as `forecast_zone`, `marine`, `invalid_county_code`, `invalid_event_begin`, or `duplicate_event_id`. The outputs include the complete event assessment, prepared FEMA declaration windows, every candidate link, a candidate review queue, and a JSON summary. A unique candidate is not a confirmed match: the summary always reports zero confirmed matches and raises `candidate_links_require_review` whenever candidates exist. A reviewer must evaluate the source context before any analytical linkage is accepted.

## Prototype recovery-equity score

For county *i*, each observed component is converted to a national percentile rank:

- declaration rate;
- documented loss per resident;
- CDC/ATSDR overall Social Vulnerability Index rank; and
- funding gap, defined in a later milestone after the funding/loss relationship is validated.

The prototype score is:

`100 × Σ(weight × component percentile) / Σ(observed component weights)`

The default weights are equal. In public releases, the score will be withheld unless all four components are observed. Sensitivity analysis will compare rankings under alternative defensible weights.

## Interpretation

A higher score indicates a stronger combination of recorded exposure, harm, vulnerability, and potential unmet funding need. It does **not** establish that a county was denied aid, that an agency acted unfairly, or that additional funding would necessarily produce a particular outcome.

## Validation gates before national publication

- Verify record counts against each source's published metadata.
- Quantify unmatched and non-county FEMA records.
- Reconcile disaster numbers and time windows across FEMA and NOAA.
- Retain ACS margins of error for published estimates.
- Review nominal-dollar versus inflation-adjusted comparisons.
- Compare results with and without extreme-loss events.
- Publish score-component coverage and ranking sensitivity.
- Prevent partial current-year data from being compared with complete years without a visible warning.
