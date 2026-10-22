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
