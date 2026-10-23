# Contributing to RecoveryLens

RecoveryLens welcomes reproducible improvements to its data pipelines, validation, analysis, documentation, and decision surface.

## Before starting

1. Search existing issues and pull requests.
2. Open or claim an issue for material changes.
3. Keep each branch focused on one reviewable objective.

Use short branch names such as:

- `feat/fema-funding-pipeline`
- `fix/county-fips-normalization`
- `docs/scoring-limitations`

## Local checks

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
ruff check .
pytest
```

New transformations should include tests for expected records, missing fields, malformed values, and geographic edge cases.

## Wiki changes

The reviewable source for the GitHub Wiki lives in [`wiki/`](wiki/). Propose Wiki changes through the same issue, branch, and pull-request workflow as code changes. After a change reaches `main`, the `Publish Wiki` workflow copies the reviewed pages into the Wiki's separate Git history.

Avoid editing a managed Wiki page directly on GitHub except for urgent recovery. A later source-controlled update will replace changes to the same file.

## Commit and pull-request standards

- Write imperative commit subjects: `Add NOAA damage parser`.
- Explain why a change is needed, not only what files changed.
- Do not commit raw government extracts, credentials, generated caches, or private data.
- Link the pull request to an issue when one exists.
- Include source URLs and retrieval assumptions for new data.
- Describe validation evidence and known limitations.
- Keep automated checks passing before requesting review.

## Data-method changes

A pull request that changes a published metric or score must include:

- the previous and proposed definitions;
- the policy or analytical rationale;
- expected directional effects;
- missing-data behavior;
- at least one sensitivity or regression test; and
- corresponding methodology documentation.

## Review principle

Accuracy, traceability, and honest uncertainty take priority over visual polish or a more dramatic result.
