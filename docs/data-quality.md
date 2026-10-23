# Data quality and review rules

Each `pa-quality-report` run writes the same evidence in two forms:

- `quality_report.json` for automated checks, archival metadata, and downstream pipelines;
- `quality_report.md` for reviewers who need a concise, readable audit record.

The report captures the OpenFEMA endpoint, UTC retrieval timestamp, typed filter parameters, API filter expression, selected fields, ordering, page size, and record limit. It then records source and curated schemas, row counts, duplicate diagnostics, per-field null rates, financial-field coverage, county-attribution coverage, obligation-category coverage, timing coverage, and ordered validation checks.

## Validation states and warning levels

| Report status | Highest severity | Interpretation |
|---|---|---|
| `passed` | `none` | No configured quality warning was triggered. |
| `warning` | `warning` | The outputs remain available, but the named condition must be reviewed and disclosed before publication. |
| `failed` | `error` | A blocking condition exists; do not publish analytical results from this run. Retain the report and diagnostic extracts. |

Warnings are not silently converted into failures, and failures do not delete intermediate evidence. Examples of warnings include exact duplicates, missing financial values, reconciliation variances, missing or unmapped work categories, incomplete obligation dates, invalid chronology, and county-attribution rates below configured thresholds. Examples of errors include an empty source result, no curated records, conflicting project keys, or coverage that is blocked because a required denominator is unavailable.

## Metric interpretation

Null rates use the row count for the named stage as their denominator. A zero-row stage reports a null rate of `null`/“Not available” rather than dividing by zero. Financial-field coverage is reported separately for source and curated records.

County record coverage uses all curated projects. County obligation coverage uses absolute nonmissing `totalObligated` values so negative adjustments cannot cancel positive obligations and inflate the rate. Net obligated dollars remain visible for financial interpretation.

Duplicate and reconciliation warnings show that curation changed the source representation; they do not by themselves prove a bad source record. Conflicting project-key groups are error-level because the pipeline excludes them rather than choosing an unsupported value.

Obligation timing coverage counts only intervals supported by present, chronological timestamps. Timing warnings do not imply avoidable delay: the declaration date is not the project-submission date, and later obligation adjustments may occur for legitimate reasons.

NOAA damage parsing uses four explicit states: `parsed`, `reported_zero`, `missing`, and `invalid`. A missing or invalid component never becomes zero. Event-level `known_total_damage_dollars` sums only valid observed components, while `is_damage_complete` identifies events for which both property and crop values are valid. Missing or invalid values, duplicate event IDs, and source-year inconsistencies trigger review flags rather than silent correction.

NOAA injury and death counts use the same explicit-state rule. Event-level details counts are the analytical totals; person-level fatality rows are a reconciliation source and are never added to those totals. The quality summary reports both event-match rate and fatality-roster coverage because many zero-death events can produce a high match rate even when historical person-level coverage is incomplete. Duplicate or conflicting fatality IDs, ambiguous event IDs, count mismatches, and unmatched rows remain visible in diagnostics.

FEMA–NOAA matching outputs are candidate assessments, not confirmed links. County equality and overlapping date windows are necessary evidence for a candidate but are not proof that the NOAA event caused, belongs to, or exhaustively represents the FEMA declaration. `unique_candidate` means exactly one declaration survived the configured rules; `ambiguous_candidates` means more than one survived; neither status authorizes automatic linkage. Forecast zones, marine areas, invalid county codes, invalid date windows, duplicate event IDs, duplicate declaration-area keys, and records that reach a configured FEMA retrieval limit remain explicit warnings or unmatchable states.

## Determinism and review

Given the same retrieved records, retrieval timestamp, query metadata, and configuration, the JSON and Markdown files are byte-stable: keys, tables, checks, precision, and output filenames use fixed ordering and formatting. Different live runs should have different retrieval timestamps and may reflect legitimate upstream revisions.

Reviewers should begin with the validation checks, trace any warning to the row counts or field-level metrics, and inspect the unmatched and duplicate extracts when applicable. A warning or failure describes fitness for the intended analysis; it is not evidence of poor agency performance, inequitable treatment, or causation.
