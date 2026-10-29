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

**Status: Implemented and bounded live-validated; source warnings remain visible.**

- [x] Version-aware annual bulk downloads
- [x] Property and crop damage parsing
- [x] Injury and fatality aggregation
- [x] Event-to-declaration matching assessment — [PR #20](https://github.com/Boatengs/recoverylens/pull/20)
- [x] Inflation-adjusted loss measures — [method and validation](inflation.md)

## Milestone 4 — Population and vulnerability

**Status: Implemented and live-validated for the 2022 same-vintage county universe.**

- [x] Census ACS population and socioeconomic variables
- [x] Margins-of-error and controlled-estimate status retention
- [x] CDC/ATSDR national SVI 2022 integration
- [x] County universe validation; unmatched and cross-vintage keys withheld

See [county context](county-context.md). Cross-vintage allocation is not implemented.

## Milestone 5 — Analysis and modeling

**Status: Complete for the North Carolina pilot (v1.0); independent review outstanding.**

- [x] Review-gated funding-per-resident and funding-to-loss indicators
- [x] Deterministic county-year typology clustering
- [x] Descriptive residual/outlier diagnostics (no causal funding-gap claim)
- [x] Chronological holdout and parameter sensitivity evaluation code
- [x] Model card and limitations report
- [x] Pilot panel: reviewed links, fixed funding window, transaction-year prices, empirical holdout — [pilot release](pilot-release.md)
- [ ] Independent interpretation review
- [ ] National panel

## Milestone 6 — Public decision surface

**Status: Pilot surface released in the Streamlit explorer; national map not started.**

- [x] County map (pilot counties)
- [x] Declaration and funding-window filters
- [x] County profiles and component explanations
- [x] Downloadable filtered results
- [x] Methodology and source panels
- [ ] National county map, state and disaster-type filters

## Milestone 7 — Portfolio release

- [x] Reproducible tagged release (`v1.0.0`, pilot scope)
- [x] Technical report and executive summary — [pilot release](pilot-release.md)
- [x] Portfolio case study — [case study](case-study.md)
- [ ] Demonstration video and social preview
