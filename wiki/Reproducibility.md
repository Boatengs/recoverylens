# Reproducibility

A RecoveryLens result should be traceable from an official source to a command, exact input identity, transformation, validation status, and documented limitation.

## Environment

```bash
git clone https://github.com/Boatengs/recoverylens.git
cd recoverylens
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
ruff check .
pytest
```

Python 3.11 or newer is required.

## Reproducible NOAA run

```bash
recoverylens noaa-download --dataset details --start-year 2020 --end-year 2021
recoverylens noaa-download --dataset fatalities --start-year 2020 --end-year 2021
recoverylens noaa-damage --start-year 2020 --end-year 2021
recoverylens noaa-impacts --start-year 2020 --end-year 2021
```

Archive the generated manifest and summary files with any published analysis. The manifest identifies exact filenames, NOAA creation dates, retrieval timestamps, compressed sizes, and SHA-256 checksums.

## Reproducible FEMA review run

```bash
recoverylens pa-quality-report \
  --state MA \
  --start-year 2020 \
  --max-records 500
```

Retain both `quality_report.json` and `quality_report.md`. They capture request metadata, schemas, row counts, duplicate diagnostics, null rates, financial coverage, county attribution, obligation measures, and ordered validation checks.

## Reproduction record

Record the following with an analytical result:

- RecoveryLens commit SHA or release tag;
- Python version and dependency environment;
- full command and explicit arguments;
- retrieval timestamp and upstream version or vintage;
- raw-file manifest or API request metadata;
- generated `summary.json` or quality report;
- warning and failure states; and
- any manual inclusion, exclusion, or interpretation decision.

## Determinism boundary

Given the same records, retrieval metadata, and configuration, RecoveryLens writes stable ordered outputs. A later live run may differ because an agency revised its source. That is expected; the earlier manifest or request record is what makes the change auditable.

## Repository hygiene

Do not commit raw government extracts, generated analysis outputs, virtual environments, caches, credentials, or private data. Commit code, tests, compact fixtures, and documentation needed to reproduce the result.
