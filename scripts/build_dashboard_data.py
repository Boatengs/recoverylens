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
        return {
            "replayed": True,
            "detail": "Sources match the reviewed snapshots; decisions replayed.",
        }
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
    status = {
        "built_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "release_posture": "Pre-release evidence explorer. Bounded pilot only; no rankings, scores "
        "or funding-gap estimates.",
        "milestone_5_complete": bool(evidence["m5-pilot-2026-10-24.json"]["milestone_5_complete"]),
        "review": review,
        "review_ledger": {
            "reviewer": episodes["reviewer"],
            "review_date": episodes["review_date"],
            "sha256": sha256(Path("docs/reviews/pilot-episodes.json")),
        },
        "funding_status": funding_status,
        "inflation_available": processed["inflation"] is not None,
        "gates": {
            "historical_availability_verified": False,
            "model_context_approved": False,
            "geography_reviewed": False,
            "independent_review_complete": False,
            "model_linkage_approved": False,
            "national_model_ready": False,
        },
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
