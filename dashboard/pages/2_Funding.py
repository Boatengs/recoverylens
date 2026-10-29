"""Public Assistance obligations: categories, county attribution, timing, reconciliation."""

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
    usd_m,
)

page_setup("Funding")
require_data()
info = status()

st.title("Public Assistance funding")
gate_banner()

disaster = st.selectbox("Declaration", [4393, 4465, 4543], format_func=disaster_label)
summary = next(s for s in info["funding_status"] if s["disaster_number"] == disaster)
c = st.columns(4)
c[0].metric("Projects analyzed", f"{summary['project_count']:,}")
c[1].metric("Damage category coverage", f"{summary['category_coverage_rate']:.1%}")
c[2].metric("Median days, declaration to first obligation",
            f"{summary['first_obligation_days_median']:,.0f}"
            if summary["first_obligation_days_median"] is not None else "n/a")
c[3].metric("Timing check status", summary["publication_status"])

left, right = st.columns(2)
with left:
    cat = csv("funding_by_category.csv")
    cat = cat.loc[cat.disaster_number.eq(disaster)]
    fig = px.bar(cat, x="net_total_obligated", y="damage_category_label", orientation="h",
                 color_discrete_sequence=[BLUE],
                 labels={"net_total_obligated": "Net obligated ($)", "damage_category_label": ""})
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=40, b=10),
                      title="Obligations by FEMA work category")
    st.plotly_chart(fig, use_container_width=True)
with right:
    att = csv("funding_attribution.csv")
    att = att.loc[att.disaster_number.eq(disaster)]
    fig = px.bar(att, x="county_attribution_status", y="total_obligated",
                 color_discrete_sequence=[BLUE],
                 labels={"county_attribution_status": "", "total_obligated": "Obligated ($)"})
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=40, b=10),
                      title="How projects attribute to counties")
    st.plotly_chart(fig, use_container_width=True)
    attributed = att.loc[att.county_attribution_status.eq("attributed"), "total_obligated"].sum()
    footnote(f"{usd_m(attributed)} of {usd_m(att.total_obligated.sum())} attributes to a single "
             "county. Statewide and multi-county projects stay visible here and are never "
             "spread across counties.")

timing = csv("funding_timing.csv")
timing = timing.loc[timing.disaster_number.eq(disaster)]
fig = px.histogram(timing, x="days_to_first_obligation", nbins=60, color_discrete_sequence=[BLUE],
                   labels={"days_to_first_obligation": "Days from declaration to first obligation"})
fig.update_layout(height=320, margin=dict(l=10, r=10, t=40, b=10), yaxis_title="Projects",
                  title="When projects first received an obligation")
st.plotly_chart(fig, use_container_width=True)
footnote("Intervals describe recorded administrative milestones, not processing delay or the "
         "cause of any delay.")

st.subheader("Reconciliation against award activities")
recon = csv("funding_reconciliation.csv")
recon = recon.loc[recon.disaster_number.eq(disaster)].T.reset_index()
recon.columns = ["field", "value"]
recon["value"] = recon["value"].astype(str)
st.dataframe(recon, hide_index=True, use_container_width=True)
footnote("Award activities are summed per project and compared with funded project totals. "
         "Negative activities (deobligations) are kept.")
