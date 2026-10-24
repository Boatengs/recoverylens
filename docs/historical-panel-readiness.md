# Historical panel readiness

Assessment date: 24 October 2026. No national training panel is certified.

| Component | Verified evidence | Remaining requirement |
|---|---|---|
| NOAA loss prices | 2005 events converted using published annual CPI to 2022 dollars | Retain source missingness; establish the analysis scope |
| Event/declaration linkage | 1,149 unique-candidate events, 20 ambiguous-candidate events, zero confirmed matches in the 2005 assessment | Review event identity/type and overlapping declarations; document disjoint loss allocation |
| Geography | 21,328 NOAA records were unmatchable, primarily forecast zones and marine geography | Define exclusions or separately review a defensible geography mapping |
| Population/SVI | 2022 same-vintage join validated for 3,144 counties | Acquire historically available vintages; do not backdate 2022 data |
| FEMA funding | Extraction, reconciliation, attribution and timing diagnostics implemented | Establish comparable project/disaster scope, valuation dates, and observation cutoffs |
| Temporal evaluation | Training-only scaling and chronological holdout tested | Build multiple reviewed years and report actual holdout/baseline performance |

The existing 2005 assessment also has 31,479 eligible events without candidates.
They must not silently become zero-funded disasters. Current cumulative FEMA
obligations must not be represented as funding known at a historical prediction
date without dated snapshots or transaction evidence. A retrospective descriptive
analysis must state its funding observation cutoff and cannot claim forecasting
performance from unavailable historical inputs.

Next panel construction should define the retrospective estimand and funding
observation cutoff, select years with suitable released context, preserve reviewed
link evidence, price both monetary measures consistently, and enforce the
[model-card contract](model-card.md). Automatic candidate promotion would not
satisfy those requirements. Track remaining validation in
[issue #22](https://github.com/Boatengs/recoverylens/issues/22).
