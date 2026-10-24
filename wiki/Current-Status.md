# Current Status

_Status date: 23 October 2026_

## Executive status

RecoveryLens has a tested FEMA funding pipeline and four of five NOAA deliverables. Milestone 4 is implemented and live-validated for 2022 same-vintage counties. Milestone 5 code is implemented; national empirical validation remains blocked on a reviewed, price-adjusted historical panel.

| Signal | Current value |
|---|---|
| Default branch | `main` |
| Latest delivery evidence | [County context issue #21](https://github.com/Boatengs/recoverylens/issues/21) and [modeling issue #22](https://github.com/Boatengs/recoverylens/issues/22) |
| Automated tests | See the latest linked pull-request Quality checks run |
| Total test coverage | Reported by pytest in Quality checks |
| Lint | Passing |
| Remaining analytical gates | Milestone 3 inflation pipeline and Milestone 5 empirical validation |
| Release posture | Pre-release; bounded analysis only |

## Capability readiness

| Capability | Status | Evidence and limitation |
|---|---|---|
| FEMA declarations | Ready for bounded pulls | County FIPS normalization and county aggregation are tested. Historical county detail before 1964 is limited upstream. |
| FEMA funded projects | Ready for bounded pulls | Project extraction, duplicate handling, and funding reconciliation are implemented. Values are not official federal financial reports. |
| County attribution | Review-gated | Unmatched, statewide, multi-county, missing-code, and invalid-code records remain visible; default warning thresholds are 95%. |
| Obligation categories and timing | Review-gated | Categories A–G and Z are mapped; intervals describe recorded administrative milestones, not causal processing delay. |
| NOAA source acquisition | Ready for bounded year ranges | Exact revisions, retrieval timestamps, byte sizes, and SHA-256 checksums are retained in a manifest. |
| NOAA damage | Review-gated | Known totals never convert missing or invalid values to zero; reported loss is not total economic impact. |
| NOAA casualties | Review-gated | Details-table totals remain canonical; person-level fatalities are reconciliation evidence only. |
| Cross-source FEMA–NOAA matching | Review-gated | County/date candidates expose unique, ambiguous, absent, and unmatchable states; no candidate is treated as a confirmed link. |
| Inflation adjustment | Helper implemented | Supplied annual CPI conversion retains nominal values; live CPI acquisition and pipeline integration remain outstanding. |
| ACS and national SVI | Live-validated for 2022 | 3,144 matched counties; 78 Puerto Rico municipalities withheld from the national SVI join. |
| Analysis and modeling | Code implemented; national validation blocked | Indicators, typologies, residual diagnostics, chronological holdout, and sensitivity require reviewed links and historically available context. |

## Bounded live-data evidence

### NOAA casualty reconciliation (1950)

The 1950 NOAA validation is a pipeline check, not a national estimate:

- 223 eligible unique events;
- 659 known injuries;
- 70 known deaths in the details table;
- 11 linked unique person-level fatality rows;
- 94.62% event-level death-count match rate;
- 15.71% fatality-roster coverage; and
- 12 event-level count mismatches, producing a `warning` state.

The high event-match rate and low roster coverage are not contradictory. Many zero-death events can match while the historical person-level roster still covers only a small fraction of deaths reported in the details table. RecoveryLens preserves both measures.

Implementation and validation evidence: [PR #16](https://github.com/Boatengs/recoverylens/pull/16) and [Issue #15](https://github.com/Boatengs/recoverylens/issues/15).

### FEMA–NOAA candidate assessment (2005)

The 2005 run assessed official source records with a strict zero-day buffer:

- 53,976 NOAA event rows, of which 32,648 had eligible county geography and date windows;
- 1,553 FEMA declaration-area rows, of which 1,537 were eligible;
- 1,189 candidate links across 1,169 NOAA events;
- 1,149 unique-candidate events and 20 ambiguous-candidate events;
- 31,479 eligible events with no candidate;
- 21,328 NOAA rows retained as unmatchable, primarily forecast-zone and marine records; and
- zero confirmed matches by design.

The run status was `warning`. County/date overlap creates a review candidate, not proof that a NOAA event and FEMA declaration are the same causal event. Implementation and validation evidence: [PR #20](https://github.com/Boatengs/recoverylens/pull/20) and [Issue #19](https://github.com/Boatengs/recoverylens/issues/19).

## Recently completed

- [PR #12](https://github.com/Boatengs/recoverylens/pull/12) — version-aware NOAA Storm Events downloads
- [PR #14](https://github.com/Boatengs/recoverylens/pull/14) — property and crop damage parsing
- [PR #16](https://github.com/Boatengs/recoverylens/pull/16) — injury and fatality aggregation
- [PR #20](https://github.com/Boatengs/recoverylens/pull/20) — FEMA–NOAA candidate-link assessment

## Next release gates

1. Add inflation-adjusted loss measures while retaining nominal values and price-base metadata.
2. Assemble a reviewed county-year panel with complete funding/loss coverage.
3. Supply historically available context and document geography and source review.
4. Validate all components together before publishing national comparisons or rankings.

For the full delivery sequence, see the [[Roadmap]].

## County context validation

The four official source downloads were checksum-verified: 3,222 ACS rows and 3,144 national SVI rows, with all SVI keys matched. All 78 unmatched ACS keys are Puerto Rico municipalities. Population MOEs comprise 3,095 controlled estimates and 127 observed margins; controlled values never become zero uncertainty. One matched county lacks a numeric income estimate. See the [county context guide](https://github.com/Boatengs/recoverylens/blob/main/docs/county-context.md) and [model card](https://github.com/Boatengs/recoverylens/blob/main/docs/model-card.md).
