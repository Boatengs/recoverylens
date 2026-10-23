# Data Quality and Review

RecoveryLens separates pipeline execution from publication readiness. A completed command can still produce a warning or blocking condition that requires review.

## Validation states

| Status | Meaning | Reviewer action |
|---|---|---|
| `passed` | No configured warning or error was triggered. | Confirm scope and interpretation, then proceed. |
| `warning` | Outputs are available, but a named limitation or threshold requires disclosure. | Inspect diagnostics and document the limitation before publication. |
| `failed` | A blocking condition prevents defensible analytical publication. | Do not publish the result; correct the cause or narrow the claim. |

## Required review sequence

1. Confirm source URL, retrieval timestamp, filters, and requested range.
2. Check source and curated row counts.
3. Inspect duplicate, conflict, unmatched, and invalid-record counts.
4. Review reconciliation variances and tolerance settings.
5. Review field coverage and missing-value states.
6. Confirm the publication status and every contributing check.
7. Read the metric-specific limitation before interpreting a difference.

## Key safeguards

### FEMA funding

- Exact duplicate project keys can be collapsed; conflicting key groups are excluded and retained for diagnosis.
- Internal source-to-curated reconciliation does not prove equivalence to official financial reporting.
- County obligation coverage uses absolute nonmissing obligations so deobligations cannot cancel positive values and inflate coverage.
- Statewide, multi-county, missing-code, and invalid-code records are never silently forced into a county.

### Obligation timing

- Intervals require present, chronological timestamps.
- The declaration date is not the application or project-submission date.
- Timing outputs do not by themselves measure agency performance, applicant performance, or community recovery speed.

### NOAA damage

- Values use `parsed`, `reported_zero`, `missing`, or `invalid` states.
- Missing and invalid values never become zero.
- A known partial total is not described as complete damage.
- NOAA-reported damage is not a comprehensive estimate of economic loss.

### NOAA casualties

- Event details supply the published injury and death totals.
- Person-level fatality rows are used for reconciliation and are never added to details totals.
- Duplicate, conflicting, ambiguous, invalid, and unlinked records remain visible.
- Event-match rate and fatality-roster coverage are reported separately because they answer different questions.

### FEMA–NOAA candidate links

- County equality and overlapping date windows create review candidates, not confirmed causal links.
- Any generated candidate raises `candidate_links_require_review`; even a unique candidate is not publication-ready as a confirmed link.
- Every NOAA row retains a unique, ambiguous, no-candidate, or specific unmatchable state.
- Forecast zones and marine areas are not silently converted to counties.
- Duplicate event IDs, duplicate declaration-area keys, invalid dates, and invalid county codes are excluded from candidate generation and retained for diagnosis.
- A nonzero date buffer is recorded and raises a warning; actual overlap days and date gaps remain visible.
- Reaching the configured FEMA record limit raises a truncation warning.

## Claims the project does not support yet

- that one county was unfairly denied funding;
- that a recorded interval proves avoidable administrative delay;
- that reported storm damage captures total economic harm;
- that a unique county/date candidate proves a NOAA event and FEMA declaration are the same causal event;
- that a county-level pattern describes an individual's experience; or
- that a national RecoveryLens ranking is ready for publication.

The canonical validation definitions are in [`docs/data-quality.md`](https://github.com/Boatengs/recoverylens/blob/main/docs/data-quality.md) and [`docs/methodology.md`](https://github.com/Boatengs/recoverylens/blob/main/docs/methodology.md).
