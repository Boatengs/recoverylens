"""Methods, definitions and official sources for pilot release v1.0."""

import streamlit as st
from common import footnote, gate_banner, page_setup, require_data

page_setup("Methodology")
require_data()

st.title("Methodology and sources")
gate_banner()

st.subheader("The question this release answers")
st.markdown(
    "For three North Carolina disaster declarations (Hurricane Florence 2018, Hurricane Dorian "
    "2019, and the February 2020 storms and flooding), how much FEMA Public Assistance reached "
    "each designated county within a fixed window, relative to its residents and to the storm "
    "losses NOAA recorded there? And does a simple model using population, loss and social "
    "vulnerability account for the differences? It is a description of what happened, not a "
    "forecast and not a judgment of what any county was owed."
)

st.subheader("Definitions")
st.markdown(
    "- **Unit.** One row per county designated for Public Assistance in a pilot declaration.\n"
    "- **Funding.** Net federal share obligated in Public Assistance award activities dated within "
    "730 days of the declaration (365 days as a check), for projects coded to that county. "
    "Deobligations are kept. Every project reconciles to the cent with its funded total. "
    "Statewide, multi-county and uncoded projects are counted separately, never spread.\n"
    "- **Loss.** NOAA Storm Events known property and crop damage for events whose link to the "
    "declaration was supported in review. Missing damage stays missing.\n"
    "- **Prices.** Funding priced by obligation year and loss by event year with CPI-U annual "
    "averages (series CUUR0000SA0), in 2022 dollars.\n"
    "- **Context.** ACS 2012 to 2016 population and CDC/ATSDR SVI 2016 overall percentile. "
    "County ACS totals are controlled to official estimates, so they carry no sampling margin.\n"
    "- **Included rows.** A row enters the indicators only when its storm links are fully "
    "decided, at least one is supported, its loss record is complete and its county was screened "
    "for boundary changes. Other rows stay visible with the reason."
)

st.subheader("Link review")
st.markdown(
    "County and date overlap only makes a storm event a candidate. Each candidate was decided "
    "from the NOAA episode narrative: supported when the narrative ties the damage to the "
    "declared event, rejected when it names a different weather system, unresolved otherwise. "
    "Decisions are bound to a hash of the narrative text and replayed on every build. If the "
    "text or the candidate set changes, the build stops instead of reusing old decisions. The "
    "review was done by AI tools (Codex on 26 October, Claude on 29 October 2026) and has not "
    "been independently checked."
)

st.subheader("Model check")
st.markdown(
    "A ridge regression of log funding per resident on log population, log loss per resident "
    "and SVI is trained on 2018 and 2019 counties and scored on 2020 counties, against the "
    "training median as a baseline. Results are reported whether or not the model wins. A "
    "rerun leaving out counties with Census border notes checks sensitivity to geography."
)

st.subheader("Known limits")
st.markdown(
    "- Public Assistance and NOAA damage measure different things, so funding per dollar of "
    "loss is a ratio of unlike quantities.\n"
    "- OpenFEMA extracts are current revisions, not what was public at the time.\n"
    "- The SVI 2016 release date could not be verified; context is used retrospectively.\n"
    "- Census border notes give no population figures; flagged counties are tested by rerun.\n"
    "- Three declarations and fewer than 100 county rows cannot support national conclusions."
)

st.subheader("Official sources")
st.markdown(
    "- [OpenFEMA Public Assistance award activities]"
    "(https://www.fema.gov/openfema-data-page/public-assistance-grant-award-activities-v2)\n"
    "- [OpenFEMA Public Assistance funded project details]"
    "(https://www.fema.gov/openfema-data-page/public-assistance-funded-projects-details-v2)\n"
    "- [OpenFEMA disaster declarations summaries]"
    "(https://www.fema.gov/openfema-data-page/disaster-declarations-summaries-v2)\n"
    "- [NOAA Storm Events bulk files](https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/)\n"
    "- [CDC/ATSDR SVI 2016 county file]"
    "(https://svi.cdc.gov/Documents/Data/2016/csv/states_counties/SVI_2016_US_county.csv)\n"
    "- [BLS CPI-U bulk data](https://download.bls.gov/pub/time.series/cu/)\n"
    "- [Census controlled estimates FAQ]"
    "(https://www.census.gov/help/topics/faq.in-the-acs-data-products-i-see-a-controlled-estimate.html)\n"
    "- [Census North Carolina boundary change notes, 2014 to 2020]"
    "(https://www2.census.gov/geo/docs/reference/bndrychange/st37_nc_gcn_2014_2020.txt)"
)
footnote("Full write-up: docs/pilot-release.md in the GitHub repository.")
