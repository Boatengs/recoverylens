# Pilot boundary verification — 27 October 2026

## Finding

The Census North Carolina change-note file contains 17 county-level notes with
effective dates in 2016–2020 affecting 13 of the 61 requested pilot counties:
Ashe, Brunswick, Chatham, Cleveland, Columbus, Davidson, Gaston, Harnett, Polk,
Richmond, Robeson, Scotland and Union. Matching FIPS codes cannot certify continuity.

The screen reads all county-level entries (three-digit entity codes), excluding
five-digit place/subdivision entries. It retains multiple notes per county and
late submissions, including Davidson's 2020 correction submitted in 2023.
The other 48 counties have no matching county-level note in this file and interval;
that is not proof of unchanged boundaries.

## Reproduce and inspect

```bash
python -m recoverylens.boundary_audit \
  --county-keys data/processed/pilot_losses/candidate_review.csv
```

The command saves the exact official source with a SHA-256 digest, a county
screen, selected notes, and a summary. The committed
[evidence](evidence/boundary-audit-2026-10-27.json) binds the source and requested
county input. The result is an audit, not an approved crosswalk or model input.

## Interpretation and next decision

Census cautions that effective and submission dates do not establish which
annual product first incorporated a change. Consequently, this screen does not
automatically exclude every affected county-year or certify any unflagged county.
Each relevant comparison needs product-vintage geography evidence, a defensible
crosswalk, or a documented exclusion. No population or SVI rank is redistributed
in proportion to land area. Geography approval remains false.

Sources:
- [Census NC notes, 2014–2020](https://www2.census.gov/geo/docs/reference/bndrychange/st37_nc_gcn_2014_2020.txt)
- [Census scope and product-date caution](https://www.census.gov/programs-surveys/geography/technical-documentation/boundary-change-notes.2011-2020.html)

## Separate release-timing finding

The Census Bureau's [7 December 2017 release announcement](https://cdn.www.census.gov/newsroom/press-releases/2017/acs-5yr.html)
establishes that the ACS 2012–2016 five-year estimates were released on that date.
It does not establish the publication date or historical identity of the CDC
2016 SVI CSV imported by this project. The combined context availability gate
therefore remains unresolved. This narrows the provenance question without
mistaking an upstream ACS release for a downstream SVI release.

Dashboard and critical visualization development remain paused pending the
verification exit requirements in issue #22. The intended later design is
Tableau-style; no implementation platform has been selected.
