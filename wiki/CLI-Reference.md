# CLI Reference

The `recoverylens` command exposes bounded pipeline stages. Run commands from an activated development environment at the repository root.

## Install for development

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
ruff check .
pytest
```

## Command index

| Command | Purpose | Default output |
|---|---|---|
| `declarations` | Fetch and aggregate FEMA major-disaster declarations | `data/processed/county_declarations.csv` |
| `pa-projects` | Fetch and aggregate funded Public Assistance projects | `data/processed/county_pa_projects.csv` |
| `pa-reconcile` | Reconcile source and curated funding totals | `data/processed/pa_reconciliation/` |
| `pa-coverage` | Measure county-attribution coverage | `data/processed/pa_coverage/` |
| `pa-quality-report` | Produce JSON and Markdown run-level quality evidence | `data/processed/pa_quality/` |
| `pa-obligations` | Analyze work categories and recorded obligation timing | `data/processed/pa_obligations/` |
| `noaa-download` | Download and verify versioned annual Storm Events files | `data/raw/noaa/storm-events/` |
| `noaa-damage` | Parse verified property and crop damage values | `data/processed/noaa/damage/` |
| `noaa-impacts` | Aggregate injuries/deaths and reconcile fatality records | `data/processed/noaa/impacts/` |
| `noaa-fema-match` | Assess county/date declaration candidates without asserting confirmed links | `data/processed/noaa/fema_match/` |

## FEMA examples

```bash
# County declaration counts for a bounded state/year sample
recoverylens declarations --state MA --start-year 2020 --max-records 500

# Funded-project aggregation
recoverylens pa-projects --state MA --start-year 2020 --max-records 500

# Raw-to-curated reconciliation
recoverylens pa-reconcile --state MA --start-year 2020 --max-records 500

# County-attribution diagnostics
recoverylens pa-coverage --state MA --start-year 2020 --max-records 500

# Reviewer-facing and machine-readable quality report
recoverylens pa-quality-report --state MA --start-year 2020 --max-records 500

# Work categories and recorded obligation intervals
recoverylens pa-obligations --state MA --start-year 2020 --max-records 500
```

Use `--disaster-number` on Public Assistance commands to constrain a run to one declaration. Reconciliation tolerances and county-coverage thresholds are configurable on the relevant commands.

## NOAA examples

Download both source tables needed for casualty reconciliation:

```bash
recoverylens noaa-download --dataset details --start-year 2020 --end-year 2021
recoverylens noaa-download --dataset fatalities --start-year 2020 --end-year 2021
```

Then run the analytical stages:

```bash
recoverylens noaa-damage --start-year 2020 --end-year 2021
recoverylens noaa-impacts --start-year 2020 --end-year 2021
recoverylens noaa-fema-match --start-year 2020 --end-year 2021
```

Use `--schema-version 1.0` to pin an explicit NOAA CSV schema. Without a pin, the downloader selects the highest available numeric schema version and then its newest creation date for each year.

`noaa-fema-match` queries FEMA major-disaster declaration areas using the earliest begin date and latest end date of eligible NOAA events, including events extending into the following year. If no events are eligible, the requested years provide fallback query bounds. Its default zero-day buffer requires actual date overlap. `--date-buffer-days` expands both query bounds and can admit gaps of up to 30 days, raising a warning and retaining the actual gap. The command writes:

- `event_assessments.csv` — every NOAA row and its candidate or unmatchable state;
- `declaration_windows.csv` — prepared FEMA area windows, including ineligible rows;
- `candidate_links.csv` — every county/date candidate;
- `review_queue.csv` — unique and ambiguous candidates requiring human review; and
- `summary.json` — scope, coverage, status counts, record-limit evidence, and warnings.

A `unique_candidate` is not a confirmed event identity. Event type and FEMA incident type are retained for review but are not used through an undocumented synonym map.

## CPI-adjusted NOAA losses

```bash
python -m recoverylens.inflation --start-year 2005 --end-year 2005 --base-year 2022
```

Requires previously downloaded, manifest-verified NOAA details. Downloads published annual BLS CPI without an API key. Retains nominal values and writes adjusted event rows, annual summaries, CPI values, and provenance under `data/processed/noaa/inflation/`. Missing indexes or inconsistent event records are not silently imputed. See the [inflation guide](https://github.com/Boatengs/recoverylens/blob/main/docs/inflation.md).

## County context and exploratory modeling

```bash
python -m recoverylens.context
python -m recoverylens.modeling --panel reviewed_county_year.csv --holdout-year 2023
```

The context module downloads official 2022 ACS bulk tables and national SVI without an API key. It writes county context, a geography review queue, and source hashes. The modeling command requires an analyst-prepared, reviewed panel; the filename above is a placeholder, not a bundled dataset. See the [panel contract and model card](https://github.com/Boatengs/recoverylens/blob/main/docs/model-card.md) for required columns and historical availability gates. Outputs include county diagnostics, sensitivity comparisons, and a model report with the input hash. Synthetic test results do not establish national model validity.

## Output interpretation

- CSV files contain reviewable event-, project-, county-, disaster-, state-, or year-level tables.
- `summary.json` contains machine-readable counts, coverage, checks, and publication status.
- `quality_report.md` provides a concise human review record for Public Assistance runs.
- Unmatched and duplicate extracts are evidence, not disposable errors.
- A command completing successfully does not by itself make its results publication-ready; inspect the reported status and diagnostics.

Run `recoverylens <command> --help` for every available option.
