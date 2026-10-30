# Population uncertainty verification — 27 October 2026

## Verified methodology

Census's [2012–2016 ACS Accuracy of the Data](https://www2.census.gov/programs-surveys/acs/tech_docs/accuracy/MultiyearACSAccuracyofData2016.pdf), printed page 11, says controlled estimates marked with five asterisks have zero sampling error and use zero standard error in calculations. Page 12 explains that these errors exclude nonsampling uncertainty. Page 1 defines the estimates as period averages, not annual observations.

Therefore a verified controlled estimate can legitimately contribute zero sampling variance. That does not make the population exact or validate its use for a later disaster year. The project must verify the source annotation before applying the controlled-estimate rule.

## Exact source mapping and outstanding check

The [CDC 2016 dictionary](https://svi.cdc.gov/map25/data/docs/SVI2016Documentation_01192022.pdf), printed pages 5–6, maps `E_TOTPOP` to S0601 `HC01_EST_VC01` and `M_TOTPOP` to `HC01_MOE_VC01`. A different population table is not sufficient evidence of this field's encoding.

On 27 October 2026, the following lookup returned HTTP 200 with HTML titled `Missing Key`, not county observations:

```text
https://api.census.gov/data/2016/acs/acs5/subject?get=NAME,S0601_C01_001E,S0601_C01_001M&for=county:*&in=state:37
```

No observation was accepted from that response. API-to-dictionary field correspondence also requires verification before a comparison is accepted.

## Acceptance criteria for the next verification

- Obtain official 2016 five-year S0601 county estimates, MOEs and annotations, with field metadata and source hashes.
- Verify field correspondence to the CDC dictionary; compare all requested county keys and estimates, preserving raw annotation values.
- Classify a zero as controlled only where the upstream annotation supports it. Keep mismatches, missing records and unexplained zeros unresolved.
- Keep sampling uncertainty separate from nonsampling error, vintage alignment and geography approval.

The existing `published_zero_unreviewed` status remains accurate for the imported records. No numerical values, approval flags or model results change. Historical file availability, county geography, link review and empirical validation remain separate open gates. Dashboard development remains paused.
