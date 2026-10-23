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
```

Use `--schema-version 1.0` to pin an explicit NOAA CSV schema. Without a pin, the downloader selects the highest available numeric schema version and then its newest creation date for each year.

## Output interpretation

- CSV files contain reviewable event-, project-, county-, disaster-, state-, or year-level tables.
- `summary.json` contains machine-readable counts, coverage, checks, and publication status.
- `quality_report.md` provides a concise human review record for Public Assistance runs.
- Unmatched and duplicate extracts are evidence, not disposable errors.
- A command completing successfully does not by itself make its results publication-ready; inspect the reported status and diagnostics.

Run `recoverylens <command> --help` for every available option.
