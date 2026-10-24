# Delivery roadmap

## Milestone 1 — Foundation

- Project charter and official-source registry
- OpenFEMA declarations client
- County FIPS normalization
- Prototype transparent equity scoring
- Tests and continuous integration

## Milestone 2 — FEMA funding pipeline

**Status: Complete.**

- Public Assistance project extraction
- Disaster- and state-level reconciliation
- County attribution coverage analysis
- Obligation categories and timing measures
- Raw-to-curated data-quality report

## Milestone 3 — NOAA loss and impact pipeline

**Status: In progress.**

- [x] Version-aware annual bulk downloads
- [x] Property and crop damage parsing
- [x] Injury and fatality aggregation
- [x] Event-to-declaration matching assessment — [PR #20](https://github.com/Boatengs/recoverylens/pull/20)
- [ ] Inflation-adjusted loss measures

## Milestone 4 — Population and vulnerability

**Status: Implemented and live-validated for the 2022 same-vintage county universe.**

- [x] Census ACS population and socioeconomic variables
- [x] Margins-of-error and controlled-estimate status retention
- [x] CDC/ATSDR national SVI 2022 integration
- [x] County universe validation; unmatched and cross-vintage keys withheld

See [county context](county-context.md). Cross-vintage allocation is not implemented.

## Milestone 5 — Analysis and modeling

**Status: Implementation available; empirical national validation remains blocked.**

- [x] Review-gated funding-per-resident and funding-to-loss indicators
- [x] Deterministic county-year typology clustering
- [x] Descriptive residual/outlier diagnostics (no causal funding-gap claim)
- [x] Chronological holdout and parameter sensitivity evaluation code
- [x] Model card and limitations report
- [ ] Review linked funding/loss panels, complete price adjustment, and run empirical validation

See [model card](model-card.md). No national ranking or validated funding-gap model is released.

## Milestone 6 — Public decision surface

- National county map
- State, disaster-type, and year filters
- County profiles and component explanations
- Downloadable filtered results
- Accessible methodology and source panels

## Milestone 7 — Portfolio release

- Reproducible tagged release
- Technical report and executive summary
- Portfolio case study
- Demonstration video and social preview
