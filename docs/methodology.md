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
