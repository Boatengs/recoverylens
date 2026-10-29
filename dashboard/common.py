"""Shared data access, labels and layout for the RecoveryLens evidence explorer."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent / "data"
DISASTER_NAMES = {
    4393: "4393 Hurricane Florence (2018)",
    4465: "4465 Hurricane Dorian (2019)",
    4543: "4543 Severe storms and flooding (2020)",
    4487: "4487 COVID-19 (competing declaration)",
}
INK, MUTED, BLUE, AMBER, RED, GREEN = (
    "#1f2937", "#6b7280", "#1d4ed8", "#b45309", "#b91c1c", "#047857")
GATE_TEXT = (
    "Pre-release evidence explorer for the North Carolina 2018 to 2020 pilot. It shows what the "
    "pipeline has assembled and what review it has passed. It does not rank counties, score "
    "equity or estimate funding gaps; those stay withheld until Milestone 5 validation."
)


@st.cache_data
def csv(name: str, **kwargs) -> pd.DataFrame:
    return pd.read_csv(DATA / name, dtype={"county_fips": str}, **kwargs)


@st.cache_data
def status() -> dict:
    return json.loads((DATA / "status.json").read_text())


def require_data() -> None:
    if not (DATA / "status.json").exists():
        st.error("dashboard/data is empty. Run the Dashboard data workflow or "
                 "scripts/build_dashboard_data.py after the pilot pipeline.")
        st.stop()


def page_setup(title: str) -> None:
    st.set_page_config(page_title=f"{title} | RecoveryLens", layout="wide")
    st.markdown(
        "<style>.block-container{padding-top:2rem;max-width:1280px}"
        ".note{color:#6b7280;font-size:.85rem}</style>",
        unsafe_allow_html=True,
    )


def gate_banner() -> None:
    st.warning(GATE_TEXT, icon=":material/rule:")


def footnote(text: str) -> None:
    st.markdown(f'<p class="note">{text}</p>', unsafe_allow_html=True)


def usd_m(value) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{'-' if value < 0 else ''}${abs(value) / 1e6:,.1f}M"


def disaster_label(number) -> str:
    return DISASTER_NAMES.get(int(number), str(number))


def county_names() -> pd.Series:
    names = csv("county_centroids.csv").set_index("county_fips")["county_name"]
    return names.str.replace(" County", "", regex=False)
