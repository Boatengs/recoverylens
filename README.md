# RecoveryLens

**U.S. Disaster Recovery Funding & Equity Observatory**

RecoveryLens is an open-source decision-intelligence project for examining whether federal disaster-recovery resources align with disaster exposure, documented losses, population, and social vulnerability across U.S. counties.

The project is being built as a reproducible public-data product rather than a one-off notebook. Every published indicator will have a source, definition, transformation record, validation rule, and stated limitation.

## The policy question

> Are disaster-prone and socially vulnerable communities receiving timely, proportionate federal recovery support?

RecoveryLens will help analysts, public officials, journalists, researchers, and community organizations explore:

- where major disasters occur repeatedly;
- how documented losses compare with obligated federal assistance;
- how recovery funding varies per resident and per dollar of damage;
- whether highly vulnerable communities experience persistent funding gaps; and
- which results are robust enough to support decisions—and which require caution.

## Completed milestone: FEMA funding pipeline

The completed foundation and current funding-pipeline slice include:

- a resilient OpenFEMA API client with pagination and retry handling;
- county FIPS normalization for FEMA disaster declarations;
- county-level declaration aggregation;
- bounded Public Assistance funded-project extraction;
- county FIPS normalization that preserves unmatched records;
- county-level project and obligation aggregation;
- disaster- and state-level funding reconciliation with duplicate diagnostics;
- county-attribution coverage, warning thresholds, and unmatched-record extracts;
- FEMA work-category summaries and declaration-to-obligation timing diagnostics;
- deterministic machine- and human-readable data-quality reports;
- a transparent, configurable recovery-equity score;
- automated tests and continuous integration;
- source, methodology, and data-quality documentation.

The repository intentionally does **not** publish a national ranking yet. A ranking will only be released after funding, loss, population, and vulnerability inputs have been validated together.

## Current milestone: NOAA loss and impact pipeline

Milestone 3 begins with a version-aware NOAA/NCEI Storm Events downloader. It discovers annual details, fatalities, and locations files from the official directory; selects revisions using the schema version and NOAA creation date encoded in each filename; downloads files atomically; and records byte sizes and SHA-256 checksums in a manifest. Damage parsing and impact aggregation will follow as separately reviewed changes.

## Planned data sources

| Source | Dataset | Intended use |
|---|---|---|
| FEMA OpenFEMA | Disaster Declarations Summaries v2 | County disaster exposure and program eligibility |
| FEMA OpenFEMA | Public Assistance Funded Projects Details v2 | Federal obligations and project categories |
| NOAA/NCEI | Storm Events Database | Property damage, crop damage, injuries, and fatalities |
| U.S. Census Bureau | American Community Survey 5-year | Population and socioeconomic denominators |
| CDC/ATSDR | Social Vulnerability Index | Community vulnerability context |

See [docs/data-sources.md](docs/data-sources.md) for canonical URLs, update notes, and known limitations.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
```

Fetch and aggregate a bounded declaration sample:

```bash
recoverylens declarations --state MA --start-year 2020 --max-records 500
```

Fetch and aggregate a bounded Public Assistance sample:

```bash
recoverylens pa-projects --state MA --start-year 2020 --max-records 500
```

Generate raw-to-curated reconciliation tables and a machine-readable summary:

```bash
recoverylens pa-reconcile --state MA --start-year 2020 --max-records 500
```

Audit county attribution and preserve unmatched records:

```bash
recoverylens pa-coverage --state MA --start-year 2020 --max-records 500
```

Generate a complete run-level quality report in JSON and Markdown:

```bash
recoverylens pa-quality-report --state MA --start-year 2020 --max-records 500
```

Analyze FEMA work categories and recorded obligation timing:

```bash
recoverylens pa-obligations --state MA --start-year 2020 --max-records 500
```

Download a bounded range of versioned NOAA Storm Events files:

```bash
recoverylens noaa-download --dataset details --start-year 2020 --end-year 2021
```

See [docs/data-quality.md](docs/data-quality.md) for validation levels and reviewer guidance.

The commands write their analytical outputs to `data/processed/`. Raw and processed data are excluded from version control because the pipeline should reproduce them from official sources.

## Repository structure

```text
src/recoverylens/   Reusable data-access and metric code
tests/              Unit tests for transformations and scoring
docs/               Methodology, source registry, and project roadmap
data/               Local-only raw and processed data directories
.github/workflows/  Automated quality checks
```

## Analytical principles

1. **No causal claims from descriptive data.** RecoveryLens identifies patterns and disparities; it does not prove discrimination or causation.
2. **No hidden composite score.** Components, weights, missing-data rules, and sensitivity checks will be public.
3. **No false precision.** Suppressed, unmatched, incomplete, or unstable records will be flagged rather than silently imputed.
4. **Official sources first.** Derived data will retain source URLs, retrieval dates, and transformation metadata.
5. **Counties are not people.** County-level patterns must not be interpreted as individual outcomes.

## Status

RecoveryLens is under active development. The current code is suitable for method review and bounded data pulls, not operational emergency management or official federal reporting.

## Disclaimer

This product uses the Federal Emergency Management Agency's OpenFEMA API but is not endorsed by FEMA. FEMA and the Federal Government cannot vouch for analyses produced after the data are retrieved. OpenFEMA Public Assistance data may differ from official financial reporting systems.

## License

Code is released under the [MIT License](LICENSE). Source datasets remain subject to their respective agency terms and documentation.
