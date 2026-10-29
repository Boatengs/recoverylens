"""Release gates, county context checks and the provenance of this build."""

import json

import pandas as pd
import streamlit as st
from common import csv, footnote, gate_banner, page_setup, require_data, status

page_setup("Evidence and Gates")
require_data()
info = status()

st.title("Evidence and release gates")
gate_banner()

st.subheader("Release gates for pilot v1.0")
st.markdown(f"**Milestone 5:** {info.get('milestone_5_status', 'not recorded')}")
gates = pd.DataFrame(info["gates"]).rename(
    columns={"gate": "Gate", "status": "Status", "evidence": "Evidence"})
st.dataframe(gates, hide_index=True, use_container_width=True)
footnote("A gate marked outstanding or out of scope is a stated limit of this release, not a "
         "pending fix hidden from view.")

st.subheader("County context and boundary screen")
counties = csv("pilot_counties.csv")
names = csv("county_centroids.csv").set_index("county_fips")["county_name"]
counties["county"] = counties.county_fips.map(names)
cols = [c for c in ["county", "county_fips", "population_baseline", "population_moe_status",
                    "svi_2016_overall", "county_note_count", "boundary_screen_status"]
        if c in counties]
st.dataframe(counties[cols].sort_values("county"), hide_index=True, use_container_width=True)
flagged = int((counties.get("county_note_count", pd.Series(dtype=int)) > 0).sum())
footnote(f"{flagged} pilot counties have a Census county-level change note for 2016 to 2020 and "
         "need geography review. A county without a note is screened, not certified unchanged. "
         "2016 population and SVI are matched by exact county code; historical availability and "
         "model use are not yet approved.")

st.subheader("Build provenance")
st.markdown(f"Built {info['built_at']}. {info['release_posture']}")
with st.expander("Processed run summaries"):
    st.code(json.dumps(info["processed_summaries"], indent=2, default=str), language="json")
with st.expander("Committed evidence records (docs/evidence)"):
    st.code(json.dumps(info["committed_evidence"], indent=2, default=str), language="json")
if not info["review"]["replayed"] and info["review"].get("error"):
    footnote(f"Review replay message: {info['review']['error']}")
