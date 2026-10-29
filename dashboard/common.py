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
    "RecoveryLens pilot release v1.0: a retrospective description of three North Carolina "
    "disaster declarations, 2018 to 2020. It does not rank counties, claim causes or estimate "
    "funding gaps, and no reviewer outside the build has checked it yet."
)
YEAR_TO_DISASTER = {2018: 4393, 2019: 4465, 2020: 4543}


@st.cache_data
def csv(name: str, **kwargs) -> pd.DataFrame:
    return pd.read_csv(DATA / name, dtype={"county_fips": str}, **kwargs)


def pilot_csv(name: str) -> pd.DataFrame:
    path = DATA / "pilot" / name
    return csv(f"pilot/{name}") if path.exists() else pd.DataFrame()


def pilot_json(name: str) -> dict:
    path = DATA / "pilot" / name
    return json.loads(path.read_text()) if path.exists() else {}


def usd(value, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{'-' if value < 0 else ''}${abs(value):,.{digits}f}"


def md_usd(value, digits: int = 2) -> str:
    """Dollar amount safe inside st.markdown, where a pair of $ signs starts LaTeX."""
    return usd(value, digits).replace("$", "\\$")


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
