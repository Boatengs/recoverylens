"""NOAA loss candidates and the documentary review of storm-to-declaration links."""

import plotly.express as px
import streamlit as st
from common import (
    AMBER,
    BLUE,
    GREEN,
    csv,
    disaster_label,
    footnote,
    gate_banner,
    page_setup,
    require_data,
    status,
    usd_m,
)

page_setup("Losses and Links")
require_data()
info = status()

st.title("Storm losses and declaration links")
gate_banner()

review = info["review"]
if review["replayed"]:
    st.success(review["detail"])
else:
    st.info(review["detail"])

losses = csv("loss_candidates_by_county.csv")
per = (losses.groupby("disaster_number", as_index=False)
       .agg(candidate_events=("candidate_events", "sum"),
            complete_damage_events=("complete_damage_events", "sum"),
            known_damage_nominal=("known_damage_nominal", "sum"),
            counties=("county_fips", "nunique")))
c = st.columns(len(per))
for col, (_, row) in zip(c, per.iterrows(), strict=True):
    col.metric(disaster_label(row.disaster_number), f"{int(row.candidate_events):,} candidates")
    col.caption(f"{int(row.counties)} counties, {usd_m(row.known_damage_nominal)} known damage")
footnote("Known damage is NOAA's reported property and crop loss for candidate events with valid "
         "values, in nominal dollars. Missing or invalid values stay missing; they are never "
         "counted as zero. It is not total economic impact.")

st.subheader("Documentary review of candidate links (26 October 2026)")
counts = csv("review_counts_documented.csv")
melted = counts.melt(id_vars=["disaster_number", "label"],
                     value_vars=["supported", "unresolved", "rejected"],
                     var_name="decision", value_name="links")
melted["declaration"] = melted.disaster_number.map(disaster_label)
fig = px.bar(melted, x="links", y="declaration", color="decision", orientation="h",
             color_discrete_map={"supported": GREEN, "unresolved": AMBER, "rejected": BLUE},
             labels={"declaration": ""})
fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), barmode="stack",
                  legend=dict(orientation="h", y=-0.25))
st.plotly_chart(fig, use_container_width=True)
footnote("Source: docs/pilot-link-review.md. Supported means a NOAA episode narrative names the "
         "hurricane and describes its impacts. It is a documentary review, not independent "
         "approval, and it does not allocate every reported dollar.")

st.subheader("Reviewed NOAA episodes")
episodes = csv("review_episodes.csv")
episodes["declaration"] = episodes.disaster_number.map(disaster_label)
st.dataframe(episodes[["declaration", "episode_id", "decision", "reason", "excerpt"]],
             hide_index=True, use_container_width=True)
footnote(f"Ledger SHA-256 {info['review_ledger']['sha256'][:16]}... Each decision is tied to the "
         "exact narrative text it was made on.")
