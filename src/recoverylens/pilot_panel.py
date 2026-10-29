"""Build the reviewed North Carolina 2018-2020 county-declaration panel.

Retrospective description only. One row per county designated for Public Assistance
in each pilot declaration. Funding is net federal share obligated within a fixed
horizon after the declaration date, priced by obligation year. Losses are NOAA's
known reported damage for documentary-supported links, priced by event year. Both
use annual CPI-U with a 2022 base. Nothing here is a forecast or an entitlement.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .funding_evidence import ACTIVITIES, KEYS, PROJECTS, reconcile
from .inflation import load_cpi
from .modeling import adjust_dollars
from .noaa import verified_storm_events_files
from .storm_damage import analyze_storm_event_damage, read_storm_event_details

PILOT = (4393, 4465, 4543)
BASE_YEAR = 2022
CONTEXT_REFERENCE_YEAR = 2016  # ACS 2012-2016 population, CDC/ATSDR SVI 2016


def read_pages(folder: Path, dataset: str) -> pd.DataFrame:
    pages = sorted(folder.glob(f"{dataset}-*.json"), key=lambda p: int(p.stem.split("-")[-1]))
    if not pages:
        raise FileNotFoundError(f"No saved {dataset} pages in {folder}")
    return pd.DataFrame([r for p in pages for r in json.loads(p.read_text())[dataset]])


def declaration_frame(path: Path) -> pd.DataFrame:
    records = json.loads(path.read_text())["DisasterDeclarationsSummaries"]
    frame = pd.DataFrame(records)
    frame = frame.loc[frame.disasterNumber.isin(PILOT)].copy()
    frame["county_fips"] = (frame.fipsStateCode.astype(str).str.zfill(2)
                            + frame.fipsCountyCode.astype(str).str.zfill(3))
    frame = frame.loc[frame.county_fips.str[2:].ne("000")]
    frame["declaration_date"] = pd.to_datetime(frame.declarationDate, utc=True)
    pa = frame.loc[frame.paProgramDeclared.astype(bool)]
    return pa[["disasterNumber", "county_fips", "designatedArea", "declaration_date"]].rename(
        columns={"disasterNumber": "disaster_number", "designatedArea": "designated_area"}
    ).drop_duplicates(["disaster_number", "county_fips"])


def county_funding(raw_root: Path, declarations: pd.DataFrame, cpi: pd.DataFrame,
                   horizon_days: int) -> tuple[pd.DataFrame, list[dict]]:
    rows, audit = [], []
    for number in PILOT:
        folder = raw_root / str(number)
        activities = read_pages(folder, ACTIVITIES)
        projects = read_pages(folder, PROJECTS)
        joined, summary = reconcile(activities, projects)
        candidates = joined.loc[joined.dated_funding_candidate, KEYS]
        for key in KEYS:
            activities[key] = activities[key].astype("string").str.strip()
            projects[key] = projects[key].astype("string").str.strip()
        state = projects.stateNumberCode.astype("string").str.extract(r"^(\d+)", expand=False)
        county = projects.countyCode.astype("string").str.extract(r"^(\d+)", expand=False)
        name = projects.county.astype("string").fillna("")
        projects["county_fips"] = (state.str.zfill(2) + county.str.zfill(3)).where(
            county.notna() & county.ne("0") & county.ne("000")
            & ~name.str.contains("statewide", case=False))
        dated = activities.merge(candidates, on=KEYS).merge(
            projects[[*KEYS, "county_fips"]], on=KEYS, how="left", validate="many_to_one")
        dated["amount"] = pd.to_numeric(dated.federalShareObligated)
        dated["obligated_at"] = pd.to_datetime(dated.dateObligated, format="ISO8601", utc=True)
        start = declarations.loc[declarations.disaster_number.eq(number),
                                 "declaration_date"].min()
        dated["days_after_declaration"] = (dated.obligated_at - start).dt.days
        in_window = dated.days_after_declaration.le(horizon_days)
        priced = adjust_dollars(dated.amount, dated.obligated_at.dt.year, cpi, BASE_YEAR)
        dated["amount_2022"] = priced.adjusted_dollars
        window = dated.loc[in_window]
        attributed = window.loc[window.county_fips.notna()]
        designated = set(declarations.loc[declarations.disaster_number.eq(number),
                                          "county_fips"])
        by_county = attributed.groupby("county_fips").agg(
            funding_nominal=("amount", "sum"), funding_dollars=("amount_2022", "sum"),
            funded_projects=("pwNumber", "nunique"), activities=("id", "size")).reset_index()
        by_county.insert(0, "disaster_number", number)
        rows.append(by_county)
        audit.append({
            "disaster_number": number, "horizon_days": horizon_days,
            "declaration_date": start.date().isoformat(),
            "projects_reconciled": summary["reconciled_projects"],
            "projects_total": summary["project_rows"],
            "all_projects_dated_candidates": bool(joined.dated_funding_candidate.all()),
            "net_federal_share_all_dates_nominal": round(float(dated.amount.sum()), 2),
            "net_in_window_nominal": round(float(window.amount.sum()), 2),
            "net_in_window_county_attributed_nominal": round(float(attributed.amount.sum()), 2),
            "net_in_window_not_county_attributed_nominal": round(
                float(window.loc[window.county_fips.isna(), "amount"].sum()), 2),
            "net_in_window_attributed_outside_pa_designation_nominal": round(float(
                attributed.loc[~attributed.county_fips.isin(designated), "amount"].sum()), 2),
            "counties_attributed_outside_pa_designation": sorted(
                set(attributed.county_fips) - designated),
            "net_after_window_nominal": round(float(dated.loc[~in_window, "amount"].sum()), 2),
        })
    return pd.concat(rows, ignore_index=True), audit


def county_losses(review: pd.DataFrame, damage: pd.DataFrame, cpi: pd.DataFrame) -> pd.DataFrame:
    links = review.loc[review.disaster_number.isin(PILOT)].copy()
    links["county_fips"] = links.county_fips.astype(str).str.zfill(5)
    supported = links.loc[links.decision.eq("supported")].merge(
        damage[["event_id", "event_year", "known_total_damage_dollars", "is_damage_complete"]],
        on="event_id", how="left", validate="many_to_one")
    priced = adjust_dollars(supported.known_total_damage_dollars, supported.event_year, cpi,
                            BASE_YEAR)
    supported["loss_2022"] = priced.adjusted_dollars
    loss = supported.groupby(["disaster_number", "county_fips"]).agg(
        loss_nominal=("known_total_damage_dollars", lambda s: s.sum(min_count=1)),
        loss_dollars=("loss_2022", lambda s: s.sum(min_count=1)),
        supported_links=("event_id", "size"),
        supported_complete=("is_damage_complete", lambda s: bool(s.fillna(False).all())),
    ).reset_index()
    counts = links.pivot_table(index=["disaster_number", "county_fips"], columns="decision",
                               values="event_id", aggfunc="size", fill_value=0).reset_index()
    for decision in ("supported", "unresolved", "rejected"):
        if decision not in counts:
            counts[decision] = 0
    counts = counts.rename(columns={"unresolved": "unresolved_links",
                                    "rejected": "rejected_links"}).drop(columns="supported")
    return counts.merge(loss, on=["disaster_number", "county_fips"], how="left")


def build(args: argparse.Namespace) -> tuple[pd.DataFrame, dict]:
    cpi, cpi_source = load_cpi(args.cpi_dir)
    declarations = declaration_frame(args.declarations)
    funding, funding_audit = county_funding(args.funding_raw, declarations, cpi, args.horizon_days)
    files = verified_storm_events_files(args.noaa_dir, dataset="details", start_year=2018,
                                        end_year=2020)
    damage = analyze_storm_event_damage(read_storm_event_details(files)).events
    review = pd.read_csv(args.review, dtype={"county_fips": str})
    losses = county_losses(review, damage, cpi)
    context = pd.read_csv(args.context, dtype={"county_fips": str})
    screen = pd.read_csv(args.boundary_screen, dtype={"county_fips": str})

    panel = declarations.merge(funding, on=["disaster_number", "county_fips"], how="left")
    panel[["funding_nominal", "funding_dollars"]] = panel[
        ["funding_nominal", "funding_dollars"]].fillna(0.0)
    panel = panel.merge(losses, on=["disaster_number", "county_fips"], how="left")
    panel[["unresolved_links", "rejected_links", "supported_links"]] = panel[
        ["unresolved_links", "rejected_links", "supported_links"]].fillna(0).astype(int)
    panel = panel.merge(context[["county_fips", "population_baseline",
                                 "population_moe_reported", "RPL_THEMES"]],
                        on="county_fips", how="left", validate="many_to_one")
    panel = panel.merge(screen[["county_fips", "county_note_count"]], on="county_fips",
                        how="left", validate="many_to_one")
    complete_funding = {a["disaster_number"]: a["all_projects_dated_candidates"]
                        for a in funding_audit}
    panel["year"] = panel.declaration_date.dt.year
    panel["population"] = panel.population_baseline
    # County totals are ACS-controlled to official estimates; zero is "controlled", not
    # a measured zero-width interval.
    panel["population_moe_status"] = np.where(panel.population_moe_reported.eq(0),
                                              "controlled", "published_positive")
    panel["population_moe"] = panel.population_moe_reported
    panel["svi"] = panel.RPL_THEMES.where(panel.RPL_THEMES.between(0, 1))
    panel["price_base_year"] = BASE_YEAR
    panel["context_reference_year"] = CONTEXT_REFERENCE_YEAR
    panel["context_available_year"] = np.nan  # SVI 2016 release date not verified
    panel["linkage_reviewed"] = panel.supported_links.gt(0) & panel.unresolved_links.eq(0)
    panel["loss_complete"] = panel.supported_complete.fillna(False).astype(bool) & panel[
        "linkage_reviewed"]
    panel["funding_complete"] = panel.disaster_number.map(complete_funding).astype(bool)
    screened = panel.county_note_count.notna()
    panel["county_note_count"] = panel.county_note_count.astype("Int64")
    # Every county-level note for screened counties was read (docs/pilot-release.md);
    # an unscreened county is never treated as reviewed.
    panel["geography_reviewed"] = screened
    panel["boundary_note_flag"] = panel.county_note_count.gt(0).fillna(True).astype(bool)
    panel["source_reference"] = (
        "OpenFEMA PA award activities and funded project details; NOAA Storm Events "
        "2018-2020; CDC/ATSDR SVI 2016 county file; BLS CPI-U CUUR0000SA0 annual")
    panel = panel.drop(columns=["population_baseline", "RPL_THEMES", "supported_complete"])
    panel["declaration_date"] = panel.declaration_date.dt.date.astype(str)
    summary = {
        "estimand": "Retrospective description of county Public Assistance obligations "
                    "relative to residents and reported storm losses for three NC declarations",
        "horizon_days": args.horizon_days, "price_base_year": BASE_YEAR,
        "cpi_source": cpi_source, "funding": funding_audit,
        "rows": len(panel),
        "rows_by_year": {int(k): int(v) for k, v in panel.year.value_counts().items()},
        "linkage_reviewed_rows": int(panel.linkage_reviewed.sum()),
        "loss_complete_rows": int(panel.loss_complete.sum()),
        "boundary_flagged_rows": int(panel.boundary_note_flag.sum()),
        "boundary_unscreened_rows": int((~panel.geography_reviewed).sum()),
        "reviewer": "Documentary review (Codex 26 Oct; Claude 29 Oct); "
                    "independent review not complete",
        "independent_review_complete": False,
    }
    return panel.sort_values(["year", "county_fips"]).reset_index(drop=True), summary


def write_county_keys(declarations_path: Path, candidates_path: Path, target: Path) -> int:
    """Union of PA-designated pilot counties and storm-candidate counties."""
    designated = set(declaration_frame(declarations_path).county_fips)
    candidates = pd.read_csv(candidates_path, dtype={"county_fips": str})
    keys = sorted(designated | set(candidates.county_fips.dropna().str.zfill(5)))
    target.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"county_fips": keys}).to_csv(target, index=False)
    return len(keys)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizon-days", type=int, default=730)
    parser.add_argument("--declarations", type=Path,
                        default=Path("data/raw/pilot_losses/declarations.json"))
    parser.add_argument("--funding-raw", type=Path, default=Path("data/raw/funding_evidence"))
    parser.add_argument("--noaa-dir", type=Path, default=Path("data/raw/noaa/storm-events"))
    parser.add_argument("--review", type=Path,
                        default=Path("data/processed/pilot_link_review/documentary_review.csv"))
    parser.add_argument("--context", type=Path,
                        default=Path("data/processed/historical_context/baseline_counties_2016.csv"))
    parser.add_argument("--boundary-screen", type=Path,
                        default=Path("data/processed/boundary_audit/county_screen.csv"))
    parser.add_argument("--cpi-dir", type=Path, default=Path("data/raw/cpi"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/pilot_panel"))
    parser.add_argument("--write-county-keys", type=Path,
                        help="Only write the county key file for the context and boundary steps")
    args = parser.parse_args()
    if args.write_county_keys:
        count = write_county_keys(args.declarations, Path(
            "data/processed/pilot_losses/candidate_review.csv"), args.write_county_keys)
        print(f"{count} pilot county keys written")
        return
    panel, summary = build(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    name = f"panel_h{args.horizon_days}"
    panel.to_csv(args.output_dir / f"{name}.csv", index=False)
    (args.output_dir / f"{name}_summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n")
    print(json.dumps({k: summary[k] for k in ("rows", "rows_by_year", "linkage_reviewed_rows",
                                               "loss_complete_rows")}, indent=2))


if __name__ == "__main__":
    main()
