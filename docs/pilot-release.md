# RecoveryLens pilot release v1.0

Release date: 29 October 2026. Scope: three North Carolina disaster declarations,
4393 (Hurricane Florence, 2018), 4465 (Hurricane Dorian, 2019) and 4543 (severe
storms, tornadoes and flooding, February 2020).

## Executive summary

RecoveryLens asks whether disaster prone and socially vulnerable counties receive
timely, proportionate federal recovery support. Pilot v1.0 answers a narrower,
checkable version of that question for 98 county rows: how much FEMA Public
Assistance reached each designated county within two years of the declaration,
relative to its residents and to the storm damage NOAA recorded there, and whether
population, damage and social vulnerability account for the differences.

Findings:

1. **A simple model does not beat a naive guess.** A ridge regression on population,
   known loss per resident and SVI, trained on 2018 and 2019 counties, missed 2020
   county funding per resident by $10.06 on average. Guessing the 2018 to 2019
   median missed by $8.21. The same holds with a one year window ($4.96 against
   $4.39) and without counties that have Census border notes ($10.37 against $8.40).
2. **Much of the money cannot be placed in a county.** Within two years, 29% of
   Florence's net federal share ($182.7M of $629.4M) and 89% of the 2020 declaration's
   ($12.8M of $14.4M) went to projects not coded to a single county. Another $7.8M of
   Florence money is coded to counties outside its Public Assistance designation
   (Caldwell, Iredell and Wake), and is reported, not dropped.
3. **Funding and damage move together, loosely.** Among the 46 included rows, the
   rank correlation between funding per resident and known loss per resident is
   0.44, and with SVI 0.32. These are associations in a small sample, not effects.
4. **Most rows cannot be scored yet.** 52 of 98 rows are left out, mainly because no
   reviewed storm loss exists for them (47) or their loss record is incomplete (39).
   Each row's reason is published.

What v1.0 does not do: rank counties, call any county under or over funded, make
causal claims, forecast, or cover any state beyond North Carolina. No reviewer
outside the build has checked the interpretation; that gate is open.

## The panel

One row per county designated for Public Assistance (`paProgramDeclared`) in a pilot
declaration: 51 rows for 4393, 28 for 4465 and 19 for 4543.

| Field | Definition |
|---|---|
| Funding | Net `federalShareObligated` from Public Assistance award activities dated within 730 days of the declaration date, for projects coded to the county. Deobligations are kept. 365 days is a sensitivity run. |
| Funding scope | Only projects that reconcile to the cent with their funded total and carry valid dates and supported statuses. All 3,257 projects qualify. |
| Loss | NOAA Storm Events known property plus crop damage for events whose link to the declaration was supported in review. Missing damage stays missing. |
| Prices | Funding priced by obligation year, loss by event year, CPI-U annual averages (`CUUR0000SA0`, M13), 2022 dollars. |
| Population | ACS 2012 to 2016 county total from the CDC/ATSDR SVI 2016 county file. |
| Vulnerability | SVI 2016 overall national percentile (`RPL_THEMES`). |

A row enters the indicators only when every storm link for that county and
declaration is decided with at least one supported, its loss record is complete, its
county was screened for boundary changes, and its funding is reconciled.

### Funding in the window (nominal dollars)

| Declaration | Net in 730 days | Coded to one county | Not coded to one county | Coded outside designation | After the window |
|---|---:|---:|---:|---:|---:|
| 4393 | $629,402,025.65 | $446,725,190.62 | $182,676,835.03 | $7,753,511.46 | $161,895,996.57 |
| 4465 | $70,536,735.55 | $60,730,805.61 | $9,805,929.94 | $1,287,891.77 | -$7,094,600.47 |
| 4543 | $14,408,684.25 | $1,577,720.37 | $12,830,963.88 | $382,170.62 | -$763,879.75 |

Negative amounts after the window are net deobligations, which is why 4465 and 4543
had more money in the window than they hold today. The all dates totals match the
24 October audit for 4465 and 4543 to the cent; 4393 differs by $10,261.82
(0.001%) because FEMA revised the extract since.

## Decisions made for v1.0

**Link review replay by content.** The 26 October ledger was pinned to file hashes.
The NOAA files still match those hashes, but a fresh FEMA declarations download does
not match byte for byte, so every rebuild stopped the replay. The replay now also
accepts current files when they reproduce the reviewed narrative hashes and the exact
decision counts, with no episode outside the ledger. Any other change stops the build.

**Eight undecided episodes reviewed (29 October).** Four Florence and one Dorian
episodes were rejected because their narratives attribute the damage to a different
system (separate fronts or storm clusters before landfall or after the storm left).
The Bertie County tornado on Florence's landfall day stays unresolved: its narrative
cites a stationary boundary and neither names Florence nor rules it out. The three
February 2020 episodes were supported because their narratives describe the declared
storms, tornadoes and flooding; support applies only to events overlapping the
declared incident period. Resulting counts: 4393, 150 supported, 9 rejected,
1 unresolved; 4465, 55 supported, 5 rejected; 4543, 35 supported; competing COVID-19
links, 35 rejected. These decisions are documentary review by AI tools, not
independent approval. Ledger: [reviews/pilot-episodes.json](reviews/pilot-episodes.json).

**Retrospective mode.** CDC does not publish a release date for the SVI 2016 file,
and none could be verified. Rather than invent one, the model runs in a
retrospective mode that requires context describing conditions no later than the
disaster year (2016 here) instead of context published before it. This supports
description of past disasters and rules out any forecasting claim. The default
forecast mode is unchanged.

**Controlled population margins.** All pilot counties report a population margin of
zero. Census states that controlled estimates "are not subject to sampling
variability", and counties are among the weighting areas whose totals are controlled
to official population estimates
([Census FAQ](https://www.census.gov/help/topics/faq.in-the-acs-data-products-i-see-a-controlled-estimate.html)).
These rows are treated as controlled, not as measured zero width intervals.

**Boundary notes.** Every designated county was screened against the
[Census North Carolina change notes](https://www2.census.gov/geo/docs/reference/bndrychange/st37_nc_gcn_2014_2020.txt).
Each county level note for 2016 to 2020 describes territory moving across a county
border (the 2017 North Carolina and South Carolina line changes; Wake, Chatham and
Harnett in 2019; Ashe and Wilkes, Davidson and Forsyth in 2020). None states a
population figure, so 18 flagged rows stay in the main run and the model is rerun
without them.

## Model results

Ridge regression of log(1 + funding per resident) on log(1 + population),
log(1 + loss per resident) and SVI; alpha 1 prespecified, 0.1 and 10 as checks.
Training rows: 2018 and 2019. Holdout: 2020.

| Run | Train / holdout rows | Model MAE (alpha 0.1, 1, 10) | Baseline MAE |
|---|---|---|---:|
| 730 days | 35 / 11 | $10.08, $10.06, $10.04 | $8.21 |
| 365 days | 35 / 11 | $4.96, $4.96, $4.94 | $4.39 |
| 730 days, no border notes | 25 / 7 | $10.57, $10.37, $9.43 | $8.40 |

Standardized coefficients in the main run: log population -0.25, log loss per
resident 0.54, SVI 0.03. The model fails mainly because 2020 funding per resident is
near zero in most included counties (median $0.24 against $12.86 in 2018), with 4 of
the 11 holdout counties at zero. That reflects how the 2020 money was recorded
(statewide), not a property of those counties.

Four rows have residuals beyond three robust deviations: Columbus, Cumberland and
Scotland (2018) and Brunswick (2019), all funded well above the model's prediction.
Three deterministic clusters converged (15, 18 and 13 rows). Neither label implies a
funding gap.

### Coverage

| Group | Included / rows |
|---|---|
| 2018 | 27 / 51 |
| 2019 | 8 / 28 |
| 2020 | 11 / 19 |
| SVI below 0.33 | 2 / 5 |
| SVI 0.33 to 0.67 | 11 / 23 |
| SVI above 0.67 | 33 / 70 |
| Census border note | 14 / 18 |

Low vulnerability counties are nearly absent, so the pilot cannot say how funding
varies across the full SVI range.

## Limitations

- Public Assistance pays eligible public costs; NOAA reports property and crop damage.
  Funding per dollar of loss is a ratio of unlike quantities.
- OpenFEMA extracts are current revisions, not what was public at the time.
- Statewide and multi county projects are never spread across counties, so county
  funding understates support wherever the state runs the work.
- Only 46 rows enter the indicators. No national conclusion follows.
- Link decisions and this report were produced with AI tools and have not been
  independently reviewed.

## Reproduce

The [Dashboard data workflow](../.github/workflows/dashboard-data.yml) runs every
step from official sources and commits the outputs to `dashboard/data/pilot/`.

```bash
python -m recoverylens.pilot_panel --horizon-days 730
python -m recoverylens.modeling --mode retrospective --holdout-year 2020 \
  --panel data/processed/pilot_panel/panel_h730.csv --output-dir data/processed/modeling/h730
```

BLS refuses downloads from GitHub runners; the build then reads the committed CPI
extract and records that it did ([inflation.md](inflation.md)).
