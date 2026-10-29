# Pilot documentary link review — 26 October 2026

This review examines the 255 target candidate links from the 24 October audit,
plus 35 competing links to the COVID-19 declaration. It uses the same pinned
NOAA and FEMA extracts. It is a documentary review by Codex, not independent
expert approval or validation of a model-ready panel.

| Declaration | Source-supported | Unresolved | Rejected |
|---|---:|---:|---:|
| 4393 — Florence | 150 | 10 | 0 |
| 4465 — Dorian | 55 | 5 | 0 |
| 4543 — 2020 storms | 0 | 35 | 0 |
| 4487 — competing COVID-19 links | 0 | 0 | 35 |

The supported links belong to 11 explicitly reviewed NOAA episodes whose
narratives name Florence or Dorian and describe their impacts. County/date
compatibility was established separately by the candidate assessment. Each of
the 19 reviewed episodes has one distinct narrative across its candidate rows.
The ledger records explicit episode decisions, short source excerpts, and full
narrative hashes; it does not classify arbitrary future records by keyword.

The remaining hurricane-window episodes describe other weather configurations
without establishing the named hurricane's identity. Absence of a hurricane name
alone does not prove an event was unrelated, so these 15 links remain unresolved.
The 2020 narratives describe severe weather and flooding, but this review does
not certify their declaration attribution. Their 35 COVID-19 links are rejected
because temporal overlap is insufficient evidence for attributing those weather
events to a biological incident. Rejecting one competitor does not automatically
approve the remaining candidate.

NOAA's Florence episode narratives also differ in their stated landfall dates.
This review retains those source texts without treating every detail as verified
fact or silently correcting them. Named-episode support is narrower than an
independently verified causal allocation of every reported dollar.

## Update, 29 October 2026

The eight episodes left undecided above were reviewed from their NOAA narratives
(Claude documentary review; not independent approval). Five were rejected because the
narrative attributes the damage to a different weather system. The Bertie County
tornado of 14 September 2018 stays unresolved. The three February 2020 episodes were
supported for events overlapping the declared incident period. Current counts are in
`expected_counts` in [the ledger](reviews/pilot-episodes.json) and in the
[pilot release](pilot-release.md). Replay now also accepts current source files when
they reproduce the reviewed narrative hashes and exact decision counts.

## Replay and safeguards

```bash
python scripts/review_pilot_links.py
```

The script requires the exact snapshots from the earlier pilot audit. It verifies
NOAA manifest hashes, the FEMA declaration hash, and the reviewed narrative
hashes. Changed sources require renewed review. It retains competing declarations,
and writes every decision and its evidence to
`data/processed/pilot_link_review/documentary_review.csv` with a summary JSON.

`link_review.apply_review` rejects duplicate or unknown links, stale hashes,
missing reasons/reviewer/date, and attempts to support the same event for two
disasters. Unreviewed candidates remain unresolved. Both
`independent_review_complete` and `model_linkage_approved` remain false, including
for supported links. The model's review gate is not automatically satisfied.

See [the explicit episode ledger](reviews/pilot-episodes.json). Its SHA-256 at this
review is `58ece429cbd8e459fad128a55cee514e02134b469381aa2d6704b7e192e1bbed`.

## Still required for Milestone 5

- Resolve remaining event identity decisions and independently review allocations.
- Define comparable funding/loss scope, observation horizon, and coverage exclusions.
- Acquire and verify historical population/SVI vintages and geography.
- Apply transaction-year price conversion and evaluate actual model/baseline results.

Source support for these links does not establish complete county losses, valid
funding-to-loss coverage ratios, historical forecasting availability, or national
model accuracy. Milestone 5 remains open.
