# Roadmap

RecoveryLens is delivered in reviewable milestones. A milestone is complete only when code, tests, documentation, and validation evidence agree.

## Portfolio view

| Milestone | Scope | Status |
|---|---|---|
| 1 | Foundation | **Complete** |
| 2 | FEMA funding pipeline | **Complete** |
| 3 | NOAA loss and impact pipeline | **Complete — bounded live validation; source warnings retained** |
| 4 | Population and vulnerability | Implemented and live-validated for 2022 same-vintage counties |
| 5 | Analysis and modeling | Code implemented; national empirical validation pending |
| 6 | Public decision surface | Planned |
| 7 | Portfolio release | Planned |

## Milestone 1 — Foundation

- [x] Project charter and official-source registry
- [x] OpenFEMA declarations client
- [x] County FIPS normalization
- [x] Prototype transparent equity scoring
- [x] Automated tests and continuous integration

## Milestone 2 — FEMA funding pipeline

- [x] Public Assistance project extraction
- [x] Disaster- and state-level reconciliation
- [x] County-attribution coverage analysis
- [x] Obligation categories and timing measures
- [x] Raw-to-curated data-quality report

## Milestone 3 — NOAA loss and impact pipeline

- [x] Version-aware annual bulk downloads — [PR #12](https://github.com/Boatengs/recoverylens/pull/12)
- [x] Property and crop damage parsing — [PR #14](https://github.com/Boatengs/recoverylens/pull/14)
- [x] Injury and fatality aggregation — [PR #16](https://github.com/Boatengs/recoverylens/pull/16)
- [x] Event-to-declaration matching assessment — [PR #20](https://github.com/Boatengs/recoverylens/pull/20)
- [x] Inflation-adjusted loss measures — [method and validation](https://github.com/Boatengs/recoverylens/blob/main/docs/inflation.md)

**Milestone exit gate:** event matches must expose ambiguity and nonmatches; loss outputs must retain nominal dollars, adjusted dollars, price base, and missingness.

## Milestone 4 — Population and vulnerability

- [x] Census ACS population and socioeconomic variables
- [x] Margins-of-error and controlled-estimate status retention
- [x] CDC/ATSDR national SVI 2022 integration
- [x] Same-vintage county universe validation; unmatched keys withheld

Cross-vintage geography allocation is outside this release.

**Milestone exit gate:** every published estimate carries source vintage and uncertainty metadata where available.

## Milestone 5 — Analysis and modeling

The [2016 baseline import](https://github.com/Boatengs/recoverylens/blob/main/docs/historical-context.md) covers all 61 pilot counties. This advances historical context acquisition without certifying release timing, uncertainty interpretation, or boundary equivalence.

Documentary review now distinguishes 205 source-supported pilot links, 50 unresolved links, and 35 rejected biological-incident competitors. See the [review and limitations](https://github.com/Boatengs/recoverylens/blob/main/docs/pilot-link-review.md). Model approval remains withheld.

Latest evidence: [three-cohort funding and loss audit](https://github.com/Boatengs/recoverylens/blob/main/docs/milestone-5-audit.md). Funding reconciliation passed; loss identity and historical panel validation remain unresolved. The milestone is not complete.

- [x] Review-gated funding-per-resident and funding-to-loss indicators
- [x] County-year typology through deterministic clustering
- [x] Descriptive residual/outlier diagnostics, without causal funding-gap claims
- [x] Chronological holdout and sensitivity evaluation code
- [x] Model card and limitations report
- [ ] Reviewed historical panel, consistent funding/loss valuation, and empirical national validation

**Milestone exit gate:** component coverage, stability, and sensitivity are published before any composite ranking.

## Milestone 6 — Public decision surface

- [ ] National county map
- [ ] State, disaster-type, and year filters
- [ ] County profiles and component explanations
- [ ] Downloadable filtered results
- [ ] Accessible methodology and source panels

**Milestone exit gate:** accessibility, source traceability, and caution states work across desktop and mobile views.

## Milestone 7 — Portfolio release

- [ ] Reproducible tagged release
- [ ] Technical report and executive summary
- [ ] Portfolio case study
- [ ] Demonstration video and social preview

## Delivery policy

Each material change follows the same path:

1. Define the objective and acceptance criteria in an issue.
2. Implement one focused branch.
3. Add tests and update canonical documentation.
4. Open a linked pull request with validation evidence.
5. Merge only after automated checks pass.
6. Record completion evidence and any unresolved limitation.

The version-controlled roadmap remains available at [`docs/roadmap.md`](https://github.com/Boatengs/recoverylens/blob/main/docs/roadmap.md).
