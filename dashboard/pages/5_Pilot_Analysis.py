"""Pilot analysis: review-gated county indicators, model check and county profiles."""

import numpy as np
import plotly.express as px
import streamlit as st
from common import (
    AMBER,
    BLUE,
    GREEN,
    YEAR_TO_DISASTER,
    disaster_label,
    footnote,
    gate_banner,
    page_setup,
    pilot_csv,
    pilot_json,
    require_data,
    usd,
    usd_m,
)

page_setup("Pilot Analysis")
require_data()

st.title("Pilot analysis")
gate_banner()

REASONS = {
    "loss_unavailable_or_zero": "no supported storm loss",
    "loss_complete_not_confirmed": "loss record incomplete",
    "linkage_reviewed_not_confirmed": "storm links not fully decided",
    "funding_unavailable_or_negative": "net funding negative",
    "population_unavailable": "no population",
    "svi_unavailable": "no SVI",
    "geography_reviewed_not_confirmed": "county not screened for border changes",
    "funding_complete_not_confirmed": "funding not reconciled",
    "future_or_unknown_context": "context later than disaster",
}
COLORS = {disaster_label(n): c for n, c in zip((4393, 4465, 4543), (BLUE, AMBER, GREEN),
                                                strict=True)}

left, middle, right = st.columns(3)
window = left.radio("Funding window after declaration", ["730 days", "365 days"],
                    horizontal=True)
horizon = window.split()[0]
declaration = middle.selectbox("Declaration", ["All three", 4393, 4465, 4543],
                               format_func=lambda v: v if isinstance(v, str) else
                               disaster_label(v))
drop_flagged = right.checkbox("Leave out counties with a Census border note", value=False)

run = f"h{horizon}_no_boundary_flags" if drop_flagged and horizon == "730" else f"h{horizon}"
analysis = pilot_csv(f"model_{run}/county_analysis.csv")
report = pilot_json(f"model_{run}/model_report.json")
sensitivity = pilot_csv(f"model_{run}/sensitivity.csv")
if analysis.empty:
    st.error("Model outputs are missing from this build. Run the Dashboard data workflow.")
    st.stop()
if drop_flagged and horizon == "365":
    analysis = analysis.loc[~analysis.boundary_note_flag.astype(bool)]
    st.info("The border-note sensitivity model was run for the 730 day window only. "
            "This view filters the 365 day rows and keeps the 365 day model's scores.")

analysis["declaration"] = analysis.year.map(YEAR_TO_DISASTER).map(disaster_label)
analysis["county"] = analysis.designated_area.str.replace(r"\s*\(County\)", "", regex=True)
analysis["status"] = np.where(
    analysis.model_eligible, "included",
    "left out: " + analysis.exclusion_reasons.fillna("").map(
        lambda text: ", ".join(REASONS.get(r, r) for r in text.split(";") if r)))
view = analysis if declaration == "All three" else analysis.loc[
    analysis.year.map(YEAR_TO_DISASTER).eq(declaration)]

eligible = view.loc[view.model_eligible]
c = st.columns(4)
c[0].metric("County rows", f"{len(view)}")
c[1].metric("Included in indicators", f"{len(eligible)}")
c[2].metric("Funding in window, 2022 dollars", usd_m(view.funding_dollars.sum()))
c[3].metric("Known storm loss, 2022 dollars", usd_m(view.loss_dollars.sum()))
footnote("Funding is net federal share obligated to projects coded to that county within the "
         "window, deobligations included, priced by obligation year. Statewide and multi-county "
         "projects are not counted for any county. Loss is NOAA's known reported property and "
         "crop damage from storm events whose link to the declaration was supported by review.")

st.subheader("Does a simple model explain county funding per resident?")
if report:
    mae = float(sensitivity.loc[sensitivity.ridge_alpha.eq(1.0), "holdout_mae"].iloc[0])
    base = report["baseline_holdout_mae"]
    m = st.columns(3)
    m[0].metric("Model error on 2020 counties", usd(mae), help="Mean absolute error, dollars "
                "per resident, ridge regression trained on 2018 and 2019 counties.")
    m[1].metric("Error from guessing the 2018 to 2019 median", usd(base))
    m[2].metric("Counties trained on / tested on",
                f"{report['training_rows']} / {report['holdout_rows']}")
    panel_summary = pilot_json(f"panel_h{horizon}_summary.json")
    storms = next((f for f in panel_summary.get("funding", []) if f["disaster_number"] == 4543),
                  None)
    statewide_share = (storms["net_in_window_not_county_attributed_nominal"]
                       / storms["net_in_window_nominal"]) if storms else None
    verdict = ("The model is more accurate than the median guess."
               if mae < base else
               "The model is less accurate than simply guessing the median.")
    st.markdown(
        f"**{verdict}** Inputs are population, known loss per resident and SVI. With "
        f"{report['training_rows']} training counties, and "
        + (f"{statewide_share:.0%} of the 2020 declaration's money in this window not coded "
           "to a single county, " if statewide_share is not None else "")
        + ("this pilot gives no evidence that these three measures predict county funding. "
           if mae >= base else "the result is too small to generalize from. ") +
        "Residuals below describe this model only; they are not unmet need.")

st.subheader("County indicators")
table = view.sort_values(["county", "year"])[[
    "county", "declaration", "population", "funding_dollars", "loss_dollars",
    "funding_per_resident", "funding_to_loss", "svi", "typology", "residual_outlier",
    "status"]].rename(columns={
        "county": "County", "declaration": "Declaration", "population": "Population (ACS 2012-16)",
        "funding_dollars": "Funding, 2022 $", "loss_dollars": "Known loss, 2022 $",
        "funding_per_resident": "Funding per resident", "funding_to_loss": "Funding per $ of loss",
        "svi": "SVI 2016", "typology": "Group", "residual_outlier": "Unusual for the model",
        "status": "Status"})
for column in ("Population (ACS 2012-16)", "Funding, 2022 $", "Known loss, 2022 $"):
    table[column] = table[column].round(0)
st.dataframe(table, hide_index=True, width="stretch", column_config={
    "Population (ACS 2012-16)": st.column_config.NumberColumn(format="localized"),
    "Funding, 2022 $": st.column_config.NumberColumn(format="dollar"),
    "Known loss, 2022 $": st.column_config.NumberColumn(format="dollar"),
    "Funding per resident": st.column_config.NumberColumn(format="$%.2f"),
    "Funding per $ of loss": st.column_config.NumberColumn(format="%.2f"),
    "SVI 2016": st.column_config.NumberColumn(format="%.2f"),
})
st.download_button("Download these rows (CSV)", view.to_csv(index=False).encode("utf-8"),
                   file_name=f"recoverylens_pilot_{run}.csv", mime="text/csv")
footnote("Sorted alphabetically on purpose; this is not a ranking. Group is a deterministic "
         "cluster on population, loss per resident and SVI, fitted on 2018 and 2019 counties. "
         "Unusual for the model means the residual is more than three robust deviations from the "
         "training median. Neither label says a county was under- or over-funded.")

if len(eligible):
    st.subheader("Funding and loss per resident, included counties")
    plot = eligible.assign(loss_per_resident=eligible.loss_dollars / eligible.population)
    fig = px.scatter(plot, x="loss_per_resident", y="funding_per_resident", color="declaration",
                     hover_name="county", log_x=True, color_discrete_map=COLORS,
                     labels={"loss_per_resident": "Known loss per resident, 2022 $ (log scale)",
                             "funding_per_resident": "Funding per resident, 2022 $",
                             "declaration": ""})
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10),
                      legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, width="stretch")
    footnote("Each point is one county in one declaration. Reported storm loss and Public "
             "Assistance cover different things: PA pays eligible public costs, NOAA reports "
             "property and crop damage. The chart shows association, not cause.")

st.subheader("County profile")
county = st.selectbox("County", sorted(analysis.county.unique()))
profile = analysis.loc[analysis.county.eq(county)].sort_values("year")
for _, row in profile.iterrows():
    with st.container(border=True):
        st.markdown(f"**{row.declaration}**")
        p = st.columns(4)
        p[0].metric("Funding in window", usd(row.funding_dollars, 0))
        p[1].metric("Known storm loss", usd(row.loss_dollars, 0))
        p[2].metric("Supported / unresolved / rejected links",
                    f"{int(row.supported_links)} / {int(row.unresolved_links)} / "
                    f"{int(row.rejected_links)}")
        p[3].metric("Census border note", "yes" if row.boundary_note_flag else "no")
        st.caption(f"{row.status}. Population {row.population:,.0f}; "
                   f"SVI 2016 {row.svi:.2f}." if row.population == row.population else row.status)
