"""RecoveryLens evidence explorer: pilot scope, headline evidence and what is withheld."""

import streamlit as st
from common import (
    csv,
    disaster_label,
    footnote,
    gate_banner,
    page_setup,
    require_data,
    status,
    usd_m,
)

page_setup("Overview")
require_data()
info = status()

st.title("RecoveryLens: North Carolina pilot evidence")
st.markdown(
    "**Are disaster-prone and socially vulnerable communities receiving timely, proportionate "
    "federal recovery support?** RecoveryLens is building the evidence to answer that for U.S. "
    "counties. This explorer shows the first pilot: three North Carolina disaster declarations "
    "from 2018 to 2020."
)
gate_banner()

disasters = csv("disasters.csv")
recon = csv("funding_reconciliation.csv")
links = csv("loss_candidates_by_county.csv")

st.subheader("Declarations in the pilot")
table = disasters.assign(declaration=disasters.disaster_number.map(disaster_label))[
    ["declaration", "incident_type", "incident_begin", "incident_end", "declaration_date",
     "designated_counties", "role"]]
st.dataframe(table, hide_index=True, use_container_width=True)
footnote("COVID-19 (4487) overlaps the 2020 storm window. It is shown because county and date "
         "overlap alone made it a competing candidate for weather events.")

st.subheader("Headline evidence")
cols = st.columns(len(recon) if len(recon) else 1)
for col, (_, row) in zip(cols, recon.iterrows(), strict=False):
    col.metric(disaster_label(row.disaster_number), usd_m(float(row.project_net_dollars)),
               f"{int(row.reconciled_projects):,} of {int(row.project_rows):,} projects reconciled",
               delta_color="off")
footnote("Public Assistance net obligations, reconciled award activity by award activity to "
         "funded projects. Obligations are not payments and not unmet need. Current OpenFEMA "
         "extracts, not historical publication snapshots.")

c = st.columns(3)
c[0].metric("Pilot counties with NOAA candidates", f"{info['pilot_county_count']}")
c[1].metric("NOAA event to declaration candidates", f"{int(links.candidate_events.sum()):,}")
review = info["review"]
c[2].metric("Documentary review", "Replayed" if review["replayed"] else "Not replayed",
            review["detail"][:60] + "..." if not review["replayed"] else None, delta_color="off")
footnote("A candidate is a NOAA storm event whose county and dates overlap a declaration. It is "
         "not a confirmed causal link.")

st.subheader("What this explorer does not do")
st.markdown(
    "- It does not rank counties or publish a recovery equity score.\n"
    "- It does not compare funding with losses or call any county under- or over-funded.\n"
    "- It does not treat county and date overlap as proof that a storm caused a declaration.\n"
    "- It does not treat 2016 county context as historically verified or model-approved."
)
footnote(f"Data built {info['built_at']}. Review ledger {info['review_ledger']['review_date']} "
         f"({info['review_ledger']['reviewer']}).")
