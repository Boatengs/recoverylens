# Milestone 5 evidence audit — 24 October 2026

> **Update, 29 October 2026.** The exit requirements below were worked through for the
> pilot scope in [pilot release v1.0](pilot-release.md): link decisions recorded, a
> fixed 730 day funding window with obligation-year prices, retrospective use of 2016
> context, a boundary sensitivity run, and an empirical 2020 holdout (the model did not
> beat the median baseline). Independent interpretation review (requirement 5) remains
> open, and nothing here extends beyond North Carolina.

**Decision on 24 October: Milestone 5 is not complete. No empirical model fit is certified.**

The implementation exists, but passing software tests does not establish valid
observational data or national model performance. This audit advances a three-cohort
North Carolina pilot without weakening the release gates.

## Verified funding evidence

| Declaration | Award activity rows | Project rows | Projects reconciled exactly | Negative adjustments | Net federal obligations |
|---|---:|---:|---:|---:|---:|
| 4393 — Florence, 2018 | 3,566 | 2,669 | 2,669 | 521 | $791,308,284.04 |
| 4465 — Dorian, 2019 | 639 | 491 | 491 | 117 | $63,442,135.08 |
| 4543 — storms/tornadoes/flooding, 2020 | 212 | 97 | 97 | 22 | $13,644,804.50 |

These are current revised extract totals, not historical publication snapshots,
payments to applicants, or estimates of unmet need. All observed activity statuses
were `O`; all dates parsed. Reconciliation uses decimal arithmetic to the cent,
retains deobligations, and joins disaster number, applicant ID, and worksheet number.
No project was unmatched or imbalanced in these three extracts.

The official OpenFEMA dataset metadata explains that project versions adjust
obligations and reconcile across a project's life. It also discloses a migration
issue that previously omitted records. Therefore an obligation date alone does not
prove when a record became publicly available. Dated activities enable a future
retrospective analysis, but do not establish historical forecasting availability.

## Verified loss candidate evidence

| Declaration | Candidate rows | Counties | Candidates with both damage components | Ambiguous candidates | Confirmed links |
|---|---:|---:|---:|---:|---:|
| 4393 | 160 | 47 | 142 | 0 | 0 |
| 4465 | 60 | 17 | 53 | 0 | 0 |
| 4543 | 35 | 11 | 35 | 35 | 0 |

The audit includes competing North Carolina declarations, not only the targets.
The 2020 storm candidates also overlap declaration 4487, COVID-19, whose incident
window spans 20 January 2020–11 May 2023 in this extract. County/date overlap cannot
resolve event identity or hazard compatibility. The biological declaration is a
clear competing candidate that needs explicit rejection in a review ledger; that
rejection alone would not certify every remaining storm link.

Two reported damage components do not demonstrate complete disaster losses.
County-coded events exclude forecast zones and marine geography, and reported
property/crop losses differ in scope from Public Assistance eligible costs.
Neither unmatched events nor unreported losses may become zero by default.

## Reproduce

```bash
python -m recoverylens.funding_evidence --disaster 4393
python -m recoverylens.funding_evidence --disaster 4465
python -m recoverylens.funding_evidence --disaster 4543
recoverylens noaa-download --start-year 2018 --end-year 2020
python scripts/check_pilot_losses.py
```

The funding command saves exact response pages with URLs, timestamps, byte sizes,
and hashes. A bounded extract hitting its cap fails; missing/duplicate identities
and malformed money also fail. Unknown statuses or dates prevent a project being
classified as a dated-funding candidate even if its total balances. Pagination is
not an atomic agency snapshot; reruns may differ as upstream data change.

The [machine-readable evidence](evidence/m5-pilot-2026-10-24.json) records the exact
page hashes, NOAA revisions, counts, and decisions. Raw extracts remain outside Git.

## Remaining exit requirements

1. Record source-supported event-link decisions and disjoint loss allocations.
2. Specify a defensible funding/loss comparison, fixed observation horizon, and
   transaction-year price adjustment, preserving negative adjustments.
3. Acquire suitable historical ACS/SVI vintages and verify release availability
   and county geography; the implemented 2022 context is not a historical substitute.
4. Audit coverage and exclusions before defining the final pilot panel.
5. Fit and evaluate on that panel, publish actual baseline/holdout errors, subgroup
   coverage and sensitivity, and obtain independent interpretation review.

No national ranking, causal funding-gap estimate, or empirical accuracy claim is
supported by this audit. Closing the milestone now would be inaccurate.

## Official source references

- [Award activity dataset](https://www.fema.gov/openfema-data-page/public-assistance-grant-award-activities-v2)
- [Machine-readable dataset metadata](https://www.fema.gov/api/open/v1/OpenFemaDataSets?%24filter=name%20eq%20%27PublicAssistanceGrantAwardActivities%27)
- [Funded project details](https://www.fema.gov/openfema-data-page/public-assistance-funded-projects-details-v2)
- [North Carolina disaster public notice](https://www.ncdot.gov/news/public-meetings/Documents/2020-05-29-fema-florence-dorian-michael.pdf)
- [NOAA bulk source](https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/)
