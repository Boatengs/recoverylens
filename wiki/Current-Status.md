# Current Status

_Status date: 27 October 2026_

## Executive status

RecoveryLens has tested FEMA and NOAA pipelines, including annual CPI-adjusted losses. Milestone 4 is implemented and live-validated for 2022 same-vintage counties. Milestone 5 code is implemented; national empirical validation remains blocked on a reviewed, consistently valued historical panel.

| Signal | Current value |
|---|---|
| Default branch | `main` |
| Latest delivery evidence | [Inflation issue #24](https://github.com/Boatengs/recoverylens/issues/24); national model validation tracked in [issue #22](https://github.com/Boatengs/recoverylens/issues/22) |
| Automated tests | See the latest linked pull-request Quality checks run |
| Total test coverage | Reported by pytest in Quality checks |
| Lint | Passing |
| Remaining analytical gates | Milestone 5 reviewed historical panel and empirical validation |
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
| Inflation adjustment | Implemented and live-validated | Published annual BLS CPI adjusts verified NOAA losses; nominal values, missingness, source hashes, and exclusions retained. |
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

The [boundary screen](https://github.com/Boatengs/recoverylens/blob/main/docs/boundary-verification.md)
found 17 Census county-level notes affecting 13 of 61 pilot counties during
2016–2020. The other 48 are not certified unchanged. Product-vintage comparison
is still required. The ACS 2012–2016 release date is verified as 7 December 2017;
the imported CDC SVI file's historical release identity remains unverified.
Dashboard development is paused until the evidence review is complete; the
intended later presentation is Tableau-style.

The [2016 historical baseline](https://github.com/Boatengs/recoverylens/blob/main/docs/historical-context.md) now matches all 61 pilot counties with population and national SVI values. Raw uncertainty values and source hashes are retained. Historical availability, zero-MOE interpretation, and boundary continuity are not yet certified; model-context approval remains withheld.

The [26 October documentary link review](https://github.com/Boatengs/recoverylens/blob/main/docs/pilot-link-review.md) records 205 named-hurricane source-supported links, 50 unresolved target links, and 35 rejected COVID-19 competitor links. These decisions are tied to exact source and narrative hashes. They are not independent approval, complete loss coverage, or empirical model validation.

The [24 October Milestone 5 audit](https://github.com/Boatengs/recoverylens/blob/main/docs/milestone-5-audit.md) reconciles 4,417 award activities to all 3,257 projects across three North Carolina cohorts. This is current funding evidence, not a validated historical model. The 2020 storm candidates overlap the COVID-19 declaration, demonstrating why county/date links require substantive review. Milestone 5 remains open.

1. Define a comparable funding/loss scope, funding valuation period, and observation cutoff.
2. Assemble a reviewed county-year panel with complete funding/loss coverage.
3. Supply historically available context and document geography and source review.
4. Validate all components together before publishing national comparisons or rankings.

For the full delivery sequence, see the [[Roadmap]].

## Inflation validation

The 2005 live run processed 53,976 NOAA events using published CPI values of 195.300 (2005) and 292.655 (2022). Only 3,953 events have both damage components; the output remains `warning`. No national funding-gap claim follows from this conversion. See the [inflation guide](https://github.com/Boatengs/recoverylens/blob/main/docs/inflation.md) and [historical panel readiness](https://github.com/Boatengs/recoverylens/blob/main/docs/historical-panel-readiness.md).

## County context validation

The four official source downloads were checksum-verified: 3,222 ACS rows and 3,144 national SVI rows, with all SVI keys matched. All 78 unmatched ACS keys are Puerto Rico municipalities. Population MOEs comprise 3,095 controlled estimates and 127 observed margins; controlled values never become zero uncertainty. One matched county lacks a numeric income estimate. See the [county context guide](https://github.com/Boatengs/recoverylens/blob/main/docs/county-context.md) and [model card](https://github.com/Boatengs/recoverylens/blob/main/docs/model-card.md).
