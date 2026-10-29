"""County map of pilot evidence for one declaration at a time. Descriptive only."""

import plotly.express as px
import streamlit as st
from common import (
    BLUE,
    csv,
    disaster_label,
    footnote,
    gate_banner,
    page_setup,
    require_data,
    status,
)

page_setup("County Map")
require_data()
info = status()

st.title("County evidence map")
gate_banner()

centroids = csv("county_centroids.csv")
counties = csv("pilot_counties.csv")
funding = csv("funding_by_county.csv")
losses = csv("loss_candidates_by_county.csv")
designations = csv("designations.csv")

left, right = st.columns(2)
disaster = left.selectbox("Declaration", [4393, 4465, 4543], format_func=disaster_label)
measures = {
    "Public Assistance obligated ($)": ("funding", "total_obligated"),
    "NOAA candidate events": ("losses", "candidate_events"),
    "Known reported damage in candidate events, nominal ($)": ("losses", "known_damage_nominal"),
    "Population, ACS 2012-2016": ("context", "population_baseline"),
    "CDC SVI 2016 overall percentile": ("context", "svi_2016_overall"),
}
if info.get("inflation_available"):
    measures["Known reported damage in candidate events, 2022 dollars"] = (
        "losses", "known_damage_2022")
label = right.selectbox("Measure", list(measures))
source, column = measures[label]

frame = designations.loc[designations.disaster_number.eq(disaster), ["county_fips",
                                                                     "designated_area"]]
frame = frame.merge(centroids, on="county_fips", how="left")
if source == "funding":
    part = funding.loc[funding.disaster_number.eq(disaster), ["county_fips", column]]
elif source == "losses":
    part = losses.loc[losses.disaster_number.eq(disaster), ["county_fips", column]]
else:
    part = counties[["county_fips", column]]
frame = frame.merge(part, on="county_fips", how="left")
shown = frame.dropna(subset=["latitude", column])
shown = shown.loc[shown[column] > 0] if column != "svi_2016_overall" else shown

fig = px.scatter_geo(
    shown, lat="latitude", lon="longitude", size=column, size_max=28, hover_name="county_name",
    hover_data={column: ":,.2f", "latitude": False, "longitude": False},
    color_discrete_sequence=[BLUE],
)
# Explicit North Carolina framing; newer Streamlit plotly bundles ignore fitbounds here.
fig.update_geos(scope="usa", center=dict(lat=35.25, lon=-79.6), projection_scale=5.2,
                showsubunits=True, subunitcolor="#9ca3af", showland=True, landcolor="#f9fafb")
fig.update_layout(height=520, margin=dict(l=0, r=0, t=10, b=0))
st.plotly_chart(fig, use_container_width=True)
footnote(f"Circles sit at 2016 Census county centroids and are sized by the selected measure. "
         f"{len(frame)} counties are designated for this declaration; {len(shown)} have a value "
         "above zero for this measure. Counties without a value are not shown as zero.")

if column == "known_damage_2022":
    origin = ("a committed extract of the published BLS annual averages, because BLS refused "
              "the download from the build server"
              if info.get("cpi_source_mode") == "committed_snapshot" else "the current BLS file")
    footnote("2022 dollars use CPI-U, U.S. city average, all items, annual averages, from "
             f"{origin}. CPI measures consumer prices, not construction costs.")

st.subheader("County values")
table = frame[["designated_area", column]].rename(
    columns={"designated_area": "County", column: label}).sort_values("County")
st.dataframe(table, hide_index=True, use_container_width=True)
footnote("Sorted alphabetically on purpose. Values describe one measure at a time and are not "
         "combined, adjusted per resident or compared across measures. Funding covers projects "
         "with a single county code; statewide and multi-county projects appear on the Funding "
         "page. Damage is NOAA's known reported loss for candidate events, not total economic "
         "impact, and candidate events are not confirmed links.")
