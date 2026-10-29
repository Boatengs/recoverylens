# Exploratory county modeling: implementation and release gates

## Intended use and present status

This implementation supports method review of county funding patterns. It produces
funding-per-resident and funding-to-loss indicators, deterministic clustering,
descriptive residuals, chronological holdout errors, and sensitivity diagnostics.
It does not establish aid entitlement, discrimination, causal effects, or unmet need.

**The model has not been validated on an approved national funding/loss panel.**
Its first empirical run, on the North Carolina pilot in retrospective mode, did not
beat a training-median baseline on the 2020 holdout; see the
[pilot release](pilot-release.md).
Tests use explicitly synthetic fixtures to verify arithmetic, withholding, and
absence of holdout-target leakage. Synthetic performance is not published as
empirical model performance. Milestone 5's national validation gate remains open.

## Run

```bash
python -m recoverylens.modeling --panel reviewed_county_year.csv --holdout-year 2022
```

The caller supplies a reviewed county-year panel. No generated NOAA candidate link
is automatically accepted. Required columns:

| Field | Contract |
|---|---|
| county_fips, year | Unique county-year; five-character county key and integer year |
| population, population_moe | Positive estimate; nonnegative MOE, or explicit `population_moe_status=controlled` |
| svi | National rank in [0,1] from the appropriate vintage |
| funding_dollars, loss_dollars | Nonnegative funding and positive loss in the same constant-dollar price base |
| price_base_year | One common price year across the panel |
| context_available_year | Actual availability year, no later than observation year (forecast mode) |
| context_reference_year | Last year the context describes, no later than observation year (`--mode retrospective` only; no forecasting claim) |
| linkage_reviewed, geography_reviewed | Explicit true after review of event assignment and geography |
| funding_complete, loss_complete | Explicit true after scope and missingness review |
| source_reference | Traceable source/run reference |

Panel construction is a separate review step. A source-reference string and a
review flag document caller attestations, not independent proof. Review records
must establish the funding and loss period, project/disaster scope, disjoint event
assignment, and completeness. County boundaries must be harmonized with reviewed
crosswalks where needed. Negative funding adjustments remain a source-data fact
but are excluded from this nonnegative-response model.

The 2022 context download must not be attached to earlier years and labeled as
historically available. Use the actual release year, not the survey end year, in
`context_available_year`. Earlier vintage panels are necessary for historical fits.

## Methods

All ineligible rows remain in `county_analysis.csv` with exclusion reasons.
Point ratios use only eligible inputs. Population denominator sensitivity bounds
use estimate ± MOE; the upper ratio is withheld when the lower population bound
is nonpositive. Controlled population estimates have no invented interval. These
bounds do not include uncertainty in funding or loss.

Ridge regression fits log(1 + funding per resident) from log(1 + population),
log(1 + loss per resident), and SVI. Feature centering/scaling is learned only from
years before the holdout. Alpha 1 is prespecified; 0.1 and 10 are sensitivity cases,
not selected after observing holdout performance. The inverse-log prediction is a
descriptive transformed-scale prediction; it is not an unbiased conditional mean.
MAE and RMSE use funding per resident in the supplied price base; a training-median
baseline is reported. There must be at least 20 training rows across two years and
five holdout rows. Those are execution minima, not sufficient evidence of validity.

K-means uses sorted training rows, deterministic farthest-point initialization,
training-only standardization, and up to 100 Lloyd iterations. Cluster convergence
and centers are recorded; numeric labels carry no ordinal meaning. The default
three-cluster fit is accompanied by k=2,3,4 holdout dispersion and size checks.
Repeated counties contribute one observation per year; results are county-year
typologies and require review for unstable assignments across years.

Residuals are observed minus predicted funding per resident. An absolute deviation
greater than three scaled training MADs flags an outlier. Zero training MAD leaves
the flag unavailable. A negative residual is only a model discrepancy and must not
be labeled a quantified funding gap. Temporal holdout may contain previously seen
counties; it does not assess unseen-county or independent spatial generalization.

Outputs are `county_analysis.csv`, `sensitivity.csv`, and `model_report.json`.
The report retains input checksum, coefficients, training transforms, cluster
centers, holdout scope, baseline, exclusions, and review-required status.

## Price adjustment prerequisite

`adjust_dollars` accepts an annual CPI-U table with `year`, `cpi`, and `source_url`
and applies nominal dollars × CPI(base)/CPI(source). It retains nominal values,
base year, factor, and missingness. Missing years are not interpolated. Source
rows must be unique, finite, positive, and traceable. CPI is a general consumer
price adjustment, not a reconstruction-cost index. An official CPI acquisition
pipeline and bounded NOAA live validation are now implemented in
[`recoverylens.inflation`](inflation.md). Funding still needs an explicit valuation
period and consistent price adjustment during panel construction.

## Exit gates before national findings

1. Apply the validated CPI workflow to the chosen loss scope and price funding consistently.
2. Review event/declaration links and prevent duplicate loss allocation.
3. Construct traceable historical panels with geography and availability checks.
4. Report real holdout and baseline results, residual diagnostics, cluster stability,
   sensitivity, subgroup coverage, and spatial limitations.
5. Independently review interpretations before releasing rankings or funding-gap claims.
