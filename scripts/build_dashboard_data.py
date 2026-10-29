"""Build the compact, review-labeled tables the Streamlit evidence explorer reads.

Run after the pilot pipeline (see .github/workflows/dashboard-data.yml). Inputs are the
local outputs under data/processed/ plus the committed review ledger; outputs go to
dashboard/data/, which is version controlled.

The explorer shows evidence for the 2018-2020 North Carolina pilot only. It never builds a
ranking, composite score or funding-gap estimate, and it carries every review gate forward.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from recoverylens.fema import (
    Query,
    build_session,
    iter_records,
    pa_project_filter,
    prepare_pa_projects,
)
from recoverylens.obligations import analyze_obligation_metrics
from recoverylens.reconciliation import reconcile_pa_projects

PILOT = [4393, 4465, 4543]
COMPETITOR = 4487
PROCESSED = Path("data/processed")
OUT = Path("dashboard/data")
GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2016_Gazetteer/"
    "2016_Gaz_counties_national.zip"
)
PA_FIELDS = (
    "disasterNumber",
    "stateAbbreviation",
    "county",
    "stateNumberCode",
    "countyCode",
    "damageCategoryCode",
    "projectStatus",
    "gmProjectId",
    "projectAmount",
    "federalShareObligated",
    "totalObligated",
    "declarationDate",
    "firstObligationDate",
    "lastObligationDate",
)


def read_json(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(frame: pd.DataFrame, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUT / name, index=False)


def declarations() -> pd.DataFrame:
    path = PROCESSED.parent / "raw" / "pilot_losses" / "declarations.json"
    rows = pd.DataFrame(json.loads(path.read_text())["DisasterDeclarationsSummaries"])
    rows["county_fips"] = rows.fipsStateCode.astype(str).str.zfill(2) + rows.fipsCountyCode.astype(
        str
    ).str.zfill(3)
    return rows


def disaster_table(decl: pd.DataFrame) -> pd.DataFrame:
    keep = decl.loc[decl.disasterNumber.isin([*PILOT, COMPETITOR])]
    counties = keep.loc[~keep.county_fips.str.endswith("000")]
    out = keep.groupby("disasterNumber", as_index=False).agg(
        title=("declarationTitle", "first"),
        incident_type=("incidentType", "first"),
        incident_begin=("incidentBeginDate", "first"),
        incident_end=("incidentEndDate", "first"),
        declaration_date=("declarationDate", "first"),
        pa_declared=("paProgramDeclared", "max"),
        ia_declared=("iaProgramDeclared", "max"),
    )
    out["designated_counties"] = out.disasterNumber.map(
        counties.groupby("disasterNumber").county_fips.nunique()
    )
    out["role"] = out.disasterNumber.map(
        lambda n: "pilot" if n in PILOT else "competing declaration"
    )
    for column in ("incident_begin", "incident_end", "declaration_date"):
        out[column] = out[column].astype(str).str[:10]
    return out.rename(columns={"disasterNumber": "disaster_number"})


def designations(decl: pd.DataFrame) -> pd.DataFrame:
    rows = decl.loc[decl.disasterNumber.isin(PILOT) & ~decl.county_fips.str.endswith("000")]
    return (
        rows[
            [
                "disasterNumber",
                "county_fips",
                "designatedArea",
                "paProgramDeclared",
                "iaProgramDeclared",
            ]
        ]
        .drop_duplicates(["disasterNumber", "county_fips"])
        .rename(columns={"disasterNumber": "disaster_number", "designatedArea": "designated_area"})
    )


def centroids(fips: set[str]) -> pd.DataFrame:
    response = build_session().get(GAZETTEER_URL, timeout=120)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        member = next(n for n in archive.namelist() if n.endswith(".txt"))
        table = pd.read_csv(
            archive.open(member), sep="\t", dtype={"GEOID": str}, encoding="latin-1"
        )
    table.columns = [c.strip() for c in table.columns]
    table = table.loc[table.GEOID.isin(fips), ["GEOID", "NAME", "INTPTLAT", "INTPTLONG"]]
    return table.rename(
        columns={
            "GEOID": "county_fips",
            "NAME": "county_name",
            "INTPTLAT": "latitude",
            "INTPTLONG": "longitude",
        }
    )


def funding() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict]]:
    by_county, attribution, categories, timing, statuses = [], [], [], [], []
    for number in PILOT:
        query = Query(
            dataset="pa_projects",
            filter_expression=pa_project_filter(disaster_number=number),
            select=PA_FIELDS,
            order_by="disasterNumber asc",
        )
        prepared = prepare_pa_projects(list(iter_records(query)))
        curated = reconcile_pa_projects(prepared).curated_projects
        metrics = analyze_obligation_metrics(curated)
        attributed = curated.loc[curated.county_fips.notna()]
        county = attributed.groupby("county_fips", as_index=False).agg(
            project_count=("gmProjectId", "nunique"),
            federal_share_obligated=("federalShareObligated", "sum"),
            total_obligated=("totalObligated", "sum"),
        )
        county.insert(0, "disaster_number", number)
        by_county.append(county)
        status = curated.groupby("county_attribution_status", as_index=False).agg(
            project_count=("gmProjectId", "nunique"), total_obligated=("totalObligated", "sum")
        )
        status.insert(0, "disaster_number", number)
        attribution.append(status)
        cat = metrics.category_summary.copy()
        cat.insert(0, "disaster_number", number)
        categories.append(cat)
        projects = metrics.projects
        timing.append(
            pd.DataFrame(
                {
                    "disaster_number": number,
                    "days_to_first_obligation": projects["days_to_first_obligation"],
                    "days_to_last_obligation": projects["days_to_last_obligation"],
                }
            ).dropna(how="all", subset=["days_to_first_obligation", "days_to_last_obligation"])
        )
        statuses.append(
            {
                "disaster_number": number,
                **{
                    k: metrics.summary[k]
                    for k in (
                        "publication_status",
                        "project_count",
                        "category_coverage_rate",
                        "complete_timing_rate",
                        "first_obligation_days_median",
                        "last_obligation_days_median",
                    )
                },
            }
        )
    return (
        pd.concat(by_county),
        pd.concat(attribution),
        pd.concat(categories),
        pd.concat(timing),
        statuses,
    )


def funding_evidence() -> pd.DataFrame:
    rows = []
    for number in PILOT:
        summary = read_json(PROCESSED / "funding_evidence" / str(number) / "summary.json")
        if summary:
            rows.append({k: v for k, v in summary.items() if k not in ("sources", "limitations")})
    return pd.DataFrame(rows)


def review_status() -> dict:
    summary = read_json(PROCESSED / "pilot_link_review" / "summary.json")
    log = Path("data/processed/pilot_link_review_replay.log")
    if summary:
        basis = summary.get("replay_basis", "pinned_snapshots")
        detail = (
            "Sources match the reviewed snapshots; decisions replayed."
            if basis == "pinned_snapshots"
            else "Current NOAA and FEMA files reproduce the reviewed links and narrative text "
            "exactly, so every recorded decision was replayed."
        )
        return {"replayed": True, "detail": detail, "replay_basis": basis,
                "observed_counts": summary.get("observed_counts", {})}
    reason = (
        log.read_text().strip().splitlines()[-1] if log.exists() and log.read_text().strip() else ""
    )
    return {
        "replayed": False,
        "detail": "Current NOAA or FEMA files differ from the reviewed snapshots, so the "
        "26 October decisions were not replayed. Candidates below are unreviewed for this build.",
        "error": reason[:300],
    }


def documented_review_counts() -> pd.DataFrame:
    """The committed 26 October review table, parsed from docs/pilot-link-review.md."""
    rows = []
    for line in Path("docs/pilot-link-review.md").read_text().splitlines():
        match = re.match(
            r"\|\s*(\d{4})\s*[—-]\s*([^|]+)\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|", line
        )
        if match:
            number, label, supported, unresolved, rejected = match.groups()
            rows.append(
                {
                    "disaster_number": int(number),
                    "label": label.strip(),
                    "supported": int(supported),
                    "unresolved": int(unresolved),
                    "rejected": int(rejected),
                }
            )
    return pd.DataFrame(rows)


def losses(review: dict) -> pd.DataFrame:
    candidates = pd.read_csv(
        PROCESSED / "pilot_losses" / "candidate_review.csv", dtype={"county_fips": str}
    )
    adjusted_path = PROCESSED / "noaa" / "inflation" / "event_damage_adjusted.csv"
    if adjusted_path.exists():
        adjusted = pd.read_csv(
            adjusted_path, usecols=["event_id", "known_total_damage_dollars_adjusted"]
        )
        candidates = candidates.merge(
            adjusted.drop_duplicates("event_id"), on="event_id", how="left"
        )
    else:
        candidates["known_total_damage_dollars_adjusted"] = pd.NA
    if review["replayed"]:
        decided = pd.read_csv(
            PROCESSED / "pilot_link_review" / "documentary_review.csv",
            usecols=["event_id", "disaster_number", "decision"],
        )
        candidates = candidates.merge(decided, on=["event_id", "disaster_number"], how="left")
    else:
        candidates["decision"] = "not replayed"
    candidates["complete"] = candidates.is_damage_complete.fillna(False).astype(bool)
    grouped = candidates.groupby(["disaster_number", "county_fips"], as_index=False)
    out = grouped.agg(
        candidate_events=("event_id", "nunique"),
        ambiguous_candidates=("candidate_count", lambda s: int((s > 1).sum())),
        complete_damage_events=("complete", "sum"),
        known_damage_nominal=("known_total_damage_dollars", lambda s: s.sum(min_count=1)),
        known_damage_2022=("known_total_damage_dollars_adjusted", lambda s: s.sum(min_count=1)),
    )
    decisions = (
        candidates.pivot_table(
            index=["disaster_number", "county_fips"],
            columns="decision",
            values="event_id",
            aggfunc="nunique",
            fill_value=0,
        )
        .add_prefix("links_")
        .reset_index()
    )
    return out.merge(decisions, on=["disaster_number", "county_fips"], how="left")


def counties(fips: set[str], names: pd.DataFrame) -> pd.DataFrame:
    base = pd.DataFrame({"county_fips": sorted(fips)})
    context = PROCESSED / "historical_context" / "baseline_counties_2016.csv"
    if context.exists():
        ctx = pd.read_csv(
            context,
            dtype={"county_fips": str},
            usecols=["county_fips", "population_baseline", "RPL_THEMES", "population_moe_status"],
        )
        base = base.merge(
            ctx.rename(columns={"RPL_THEMES": "svi_2016_overall"}), on="county_fips", how="left"
        )
    screen = PROCESSED / "boundary_audit" / "county_screen.csv"
    if screen.exists():
        base = base.merge(
            pd.read_csv(screen, dtype={"county_fips": str}).drop(
                columns=["geography_reviewed"], errors="ignore"
            ),
            on="county_fips",
            how="left",
        )
    return base.merge(names, on="county_fips", how="left")


def release_gates(review: dict) -> tuple[list[dict], dict]:
    """Plain-language status and evidence for each v1.0 gate, read from the build outputs."""
    pilot = OUT / "pilot"
    panel = read_json(pilot / "panel_h730_summary.json") or {}
    model = read_json(pilot / "model_h730" / "model_report.json") or {}
    sens = pilot / "model_h730" / "sensitivity.csv"
    model_mae = None
    if sens.exists():
        table = pd.read_csv(sens)
        model_mae = float(table.loc[table.ridge_alpha.eq(1.0), "holdout_mae"].iloc[0])
    baseline_mae = model.get("baseline_holdout_mae")
    beats = model_mae is not None and baseline_mae is not None and model_mae < baseline_mae
    counts = (review.get("observed_counts") or {}) if review.get("replayed") else {}
    unresolved = sum(v for k, v in counts.items() if k.endswith("unresolved"))
    gates = [
        {"gate": "Storm-to-declaration link review (pilot)",
         "status": "documentary review complete" if review.get("replayed") else "not replayed",
         "evidence": f"{sum(counts.values())} links decided from NOAA narratives; {unresolved} "
                     "left unresolved. Codex 26 Oct, Claude 29 Oct. Replayed by content against "
                     "current NOAA and FEMA files."},
        {"gate": "Independent interpretation review", "status": "outstanding",
         "evidence": "No reviewer outside the build has checked the interpretation."},
        {"gate": "County geography",
         "status": "notes read; sensitivity run",
         "evidence": f"{panel.get('boundary_flagged_rows', 'n/a')} panel rows are in counties with "
                     "a 2016 to 2020 Census border note. The model is rerun without them."},
        {"gate": "Population uncertainty", "status": "resolved",
         "evidence": "County ACS totals are controlled to official estimates, so their zero "
                     "margins mean no sampling error is published, not a measured zero."},
        {"gate": "Context timing", "status": "retrospective use only",
         "evidence": "Context describes 2012 to 2016. The SVI 2016 release date could not be "
                     "verified, so no forecasting claim is made."},
        {"gate": "Price adjustment", "status": "complete",
         "evidence": "Obligations priced by obligation year, losses by event year; CPI-U annual "
                     "averages, 2022 dollars."},
        {"gate": "Funding observation window", "status": "fixed",
         "evidence": "Net federal share obligated within 730 days of declaration; 365 days as "
                     "a sensitivity check. Deobligations kept."},
        {"gate": "Model validation (2020 holdout)",
         "status": ("run; beats baseline" if beats else "run; does not beat baseline")
         if model_mae is not None else "not run",
         "evidence": (f"Ridge model mean absolute error ${model_mae:,.2f} per resident against "
                      f"${baseline_mae:,.2f} for the training median.")
         if model_mae is not None else "Model outputs missing from this build."},
        {"gate": "National scope", "status": "out of scope for v1.0",
         "evidence": "Three North Carolina declarations only."},
    ]
    return gates, {"model_holdout_mae": model_mae, "baseline_holdout_mae": baseline_mae,
                   "model_beats_baseline": beats}


def main() -> None:
    decl = declarations()
    disasters = disaster_table(decl)
    desig = designations(decl)
    review = review_status()
    loss = losses(review)
    pilot_fips = set(loss.county_fips)
    names = centroids(pilot_fips | set(desig.county_fips))
    by_county, attribution, categories, timing, funding_status = funding()

    write(disasters, "disasters.csv")
    write(desig, "designations.csv")
    write(counties(pilot_fips, names), "pilot_counties.csv")
    write(names, "county_centroids.csv")
    write(by_county, "funding_by_county.csv")
    write(attribution, "funding_attribution.csv")
    write(categories, "funding_by_category.csv")
    write(timing, "funding_timing.csv")
    write(funding_evidence(), "funding_reconciliation.csv")
    write(loss, "loss_candidates_by_county.csv")
    write(documented_review_counts(), "review_counts_documented.csv")
    if review.get("observed_counts"):
        current = pd.DataFrame(
            [{"disaster_number": int(k.split(":")[0]), "decision": k.split(":")[1], "links": v}
             for k, v in review["observed_counts"].items()]
        ).pivot_table(index="disaster_number", columns="decision", values="links",
                      fill_value=0).reset_index()
        for decision in ("supported", "unresolved", "rejected"):
            if decision not in current:
                current[decision] = 0
        write(current, "review_counts_current.csv")
    episodes = json.loads(Path("docs/reviews/pilot-episodes.json").read_text())
    write(
        pd.DataFrame(episodes["episodes"]).drop(columns=["narrative_sha256"]), "review_episodes.csv"
    )

    evidence = {
        name: read_json(Path("docs/evidence") / name)
        for name in (
            "m5-pilot-2026-10-24.json",
            "historical-context-2026-10-27.json",
            "boundary-audit-2026-10-27.json",
        )
    }
    processed = {
        "pilot_losses": read_json(PROCESSED / "pilot_losses" / "summary.json"),
        "historical_context": read_json(PROCESSED / "historical_context" / "summary.json"),
        "boundary_audit": read_json(PROCESSED / "boundary_audit" / "summary.json"),
        "inflation": read_json(PROCESSED / "noaa" / "inflation" / "summary.json"),
    }
    gates, model_summary = release_gates(review)
    status = {
        "built_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "release_posture": "Pilot release v1.0: retrospective description of three North "
        "Carolina declarations. No rankings, causal claims or funding-gap estimates. "
        "Independent review outstanding.",
        "milestone_5_status": "Pilot scope complete; independent review outstanding",
        "review": review,
        "review_ledger": {
            "reviewer": episodes["reviewer"],
            "review_date": episodes["review_date"],
            "sha256": sha256(Path("docs/reviews/pilot-episodes.json")),
        },
        "funding_status": funding_status,
        "inflation_available": processed["inflation"] is not None,
        "cpi_source_mode": ((processed["inflation"] or {}).get("cpi_source") or {}).get("mode"),
        "gates": gates,
        "model_summary": model_summary,
        "processed_summaries": {
            k: (
                {kk: vv for kk, vv in v.items() if kk not in ("sources", "noaa_sources")}
                if v
                else None
            )
            for k, v in processed.items()
        },
        "committed_evidence": {
            k: {kk: vv for kk, vv in v.items() if kk not in ("sources", "funding", "source")}
            for k, v in evidence.items()
            if v
        },
        "pilot_county_count": len(pilot_fips),
    }
    (OUT / "status.json").write_text(json.dumps(status, indent=2, default=str) + "\n")
    print(
        json.dumps(
            {
                "pilot_counties": len(pilot_fips),
                "review_replayed": review["replayed"],
                "inflation_available": status["inflation_available"],
                "files": sorted(p.name for p in OUT.iterdir()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
