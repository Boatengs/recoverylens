# Case study: RecoveryLens pilot v1.0

## Problem

After a major disaster, FEMA Public Assistance pays for debris removal, emergency
work and the repair of public infrastructure. Whether that money reaches the places
that were hit hardest, and the places least able to recover alone, is a fair public
question. It is also easy to answer badly. Funding records, storm damage records and
vulnerability indexes come from different agencies, describe different things and
change after publication. A quick join of the three produces confident numbers that
do not hold up.

RecoveryLens is built to answer the question slowly and checkably. Pilot v1.0 covers
three North Carolina declarations: Hurricane Florence (2018), Hurricane Dorian (2019)
and the storms and flooding of February 2020.

## Approach

Every number in the pilot can be traced to an official source and rebuilt by a
GitHub Actions workflow.

Funding comes from OpenFEMA award activities. All 3,257 projects reconcile to the
cent with their funded totals, and only money obligated within 730 days of the
declaration counts, priced in 2022 dollars by the year it was obligated.
Deobligations stay in.

Storm damage comes from NOAA Storm Events. An event that merely overlaps a
declaration in county and date is only a candidate. Each candidate was decided from
the NOAA narrative, and each decision is bound to a hash of that text. If the source
text changes, the build stops instead of reusing a stale decision. Of 290 candidate
links, 240 were supported, 49 rejected (35 of them COVID-19 links that overlapped
the 2020 storm window) and 1 left unresolved.

Population and vulnerability come from the CDC/ATSDR SVI 2016 county file. Its
release date could not be verified, so the analysis runs in a retrospective mode
that makes no forecasting claim.

## Result

A ridge model using population, damage per resident and SVI was trained on 2018 and
2019 counties and tested on 2020 counties. It missed by $10.06 per resident on
average. Guessing the earlier median missed by $8.21. The model lost, and the release
says so.

The reason is visible in the data. 89% of the 2020 declaration's money in the window
went to projects not coded to a single county, so county level funding looks near
zero even where the state carried out the work. That is a finding about how recovery
money is recorded, and it matters for anyone who builds county comparisons from
OpenFEMA.

The Streamlit explorer publishes county indicators in alphabetical order, county
profiles, the model check, every release gate with its evidence, and a CSV download.
It does not rank counties or label any county under funded.

## What is still open

No reviewer outside the build has checked the interpretation. The pilot has 98
county rows, of which 46 pass every gate, and low vulnerability counties are nearly
absent. A national version needs the same link review at far larger scale.

[Technical report](pilot-release.md) · [Repository](https://github.com/Boatengs/recoverylens)
