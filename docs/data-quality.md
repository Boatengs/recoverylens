# Public Assistance data-quality reports

Each `pa-quality-report` run writes the same evidence in two forms:

- `quality_report.json` for automated checks, archival metadata, and downstream pipelines;
- `quality_report.md` for reviewers who need a concise, readable audit record.

The report captures the OpenFEMA endpoint, UTC retrieval timestamp, typed filter parameters, API filter expression, selected fields, ordering, page size, and record limit. It then records source and curated schemas, row counts, duplicate diagnostics, per-field null rates, financial-field coverage, county-attribution coverage, and ordered validation checks.

## Validation states and warning levels

| Report status | Highest severity | Interpretation |
|---|---|---|
| `passed` | `none` | No configured quality warning was triggered. |
| `warning` | `warning` | The outputs remain available, but the named condition must be reviewed and disclosed before publication. |
| `failed` | `error` | A blocking condition exists; do not publish analytical results from this run. Retain the report and diagnostic extracts. |

Warnings are not silently converted into failures, and failures do not delete intermediate evidence. Examples of warnings include exact duplicates, missing financial values, reconciliation variances, and county-attribution rates below configured thresholds. Examples of errors include an empty source result, no curated records, conflicting project keys, or county coverage that is blocked because its denominator is unavailable.

## Metric interpretation

Null rates use the row count for the named stage as their denominator. A zero-row stage reports a null rate of `null`/“Not available” rather than dividing by zero. Financial-field coverage is reported separately for source and curated records.

County record coverage uses all curated projects. County obligation coverage uses absolute nonmissing `totalObligated` values so negative adjustments cannot cancel positive obligations and inflate the rate. Net obligated dollars remain visible for financial interpretation.

Duplicate and reconciliation warnings show that curation changed the source representation; they do not by themselves prove a bad source record. Conflicting project-key groups are error-level because the pipeline excludes them rather than choosing an unsupported value.

## Determinism and review

Given the same retrieved records, retrieval timestamp, query metadata, and configuration, the JSON and Markdown files are byte-stable: keys, tables, checks, precision, and output filenames use fixed ordering and formatting. Different live runs should have different retrieval timestamps and may reflect legitimate upstream revisions.

Reviewers should begin with the validation checks, trace any warning to the row counts or field-level metrics, and inspect the unmatched and duplicate extracts when applicable. A warning or failure describes fitness for the intended analysis; it is not evidence of poor agency performance, inequitable treatment, or causation.
