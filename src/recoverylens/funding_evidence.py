"""Reconcile dated FEMA award activities before historical funding analysis."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from .fema import build_session

ACTIVITIES = "PublicAssistanceGrantAwardActivities"
PROJECTS = "PublicAssistanceFundedProjectsDetails"
KEYS = ["disasterNumber", "applicantId", "pwNumber"]


def money(value: object) -> Decimal:
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid monetary value") from exc
    if not amount.is_finite() or amount != amount.quantize(Decimal("0.01")):
        raise ValueError("Money must be finite and stated to cents")
    return amount


def fetch(disaster: int, dataset: str, root: Path, *, limit: int = 20000) -> tuple:
    """Save exact response pages and fail rather than accept a capped extract."""
    if disaster < 1 or dataset not in (ACTIVITIES, PROJECTS):
        raise ValueError("Invalid disaster or dataset")
    root.mkdir(parents=True, exist_ok=True)
    records, pages = [], []
    session = build_session()
    for offset in range(0, limit + 1, 1000):
        url = f"https://www.fema.gov/api/open/v2/{dataset}"
        response = session.get(url, params={"$filter": f"disasterNumber eq {disaster}",
                                            "$top": 1000, "$skip": offset,
                                            "$orderby": ",".join(KEYS)}, timeout=60)
        response.raise_for_status()
        payload = response.json()
        page = payload.get(dataset)
        if not isinstance(page, list):
            raise ValueError("Unexpected FEMA response schema")
        path = root / f"{dataset}-{offset}.json"
        path.write_bytes(response.content)
        pages.append({"url": response.url, "filename": path.name,
                      "sha256": hashlib.sha256(response.content).hexdigest(),
                      "bytes": len(response.content),
                      "retrieved_at": datetime.now(UTC).isoformat(), "rows": len(page)})
        records.extend(page)
        if len(records) > limit:
            raise ValueError("Record cap exceeded; no complete extract certified")
        if len(page) < 1000:
            return pd.DataFrame(records), pages
    raise ValueError("Record cap reached without proof of end-of-data")


def reconcile(activities: pd.DataFrame, projects: pd.DataFrame) -> tuple:
    """Exact-cent project reconciliation; never claim historical availability."""
    a, p = activities.copy(), projects.copy()
    for frame, required in ((a, {*KEYS, "id", "federalShareObligated", "dateObligated",
                                  "fundingStatus", "versionNumber"}),
                            (p, {*KEYS, "federalShareObligated"})):
        if frame.empty or not required.issubset(frame):
            raise ValueError("Empty input or missing required fields")
        for key in KEYS:
            frame[key] = frame[key].astype("string").str.strip()
            if frame[key].isna().any() or frame[key].eq("").any():
                raise ValueError("Missing project identity")
    if a.id.isna().any() or a.id.astype(str).str.strip().eq("").any() or a.id.duplicated().any():
        raise ValueError("Missing or duplicate activity identifiers")
    if p.duplicated(KEYS).any():
        raise ValueError("Duplicate project identities")
    a["amount"] = a.federalShareObligated.map(money)
    p["project_amount"] = p.federalShareObligated.map(money)
    a["obligation_date"] = pd.to_datetime(
        a.dateObligated, format="ISO8601", errors="coerce", utc=True)
    a["date_valid"] = a.obligation_date.notna()
    # Unknown status is evidence to review, not permission to delete a transaction.
    a["status_supported"] = a.fundingStatus.eq("O") | (
        a.fundingStatus.eq("S") & a.amount.eq(Decimal(0)))
    grouped = a.groupby(KEYS, dropna=False).agg(
        activity_amount=("amount", "sum"), activity_rows=("id", "size"),
        dates_valid=("date_valid", "all"), statuses_supported=("status_supported", "all"),
    ).reset_index()
    joined = grouped.merge(p[KEYS + ["project_amount"]], on=KEYS, how="outer",
                           validate="one_to_one", indicator=True)
    joined["reconciled"] = joined.apply(
        lambda row: row["_merge"] == "both" and row.activity_amount == row.project_amount,
        axis=1)
    joined["dated_funding_candidate"] = (joined.reconciled
        & joined.dates_valid.astype("boolean").fillna(False)
        & joined.statuses_supported.astype("boolean").fillna(False))
    summary = {
        "publication_status": "review_required", "activity_rows": len(a),
        "project_rows": len(p), "reconciled_projects": int(joined.reconciled.sum()),
        "unreconciled_projects": int((~joined.reconciled).sum()),
        "dated_funding_candidate_projects": int(joined.dated_funding_candidate.sum()),
        "negative_activity_count": int(a.amount.lt(0).sum()),
        "invalid_date_count": int((~a.date_valid).sum()),
        "unsupported_status_count": int((~a.status_supported).sum()),
        "activity_net_dollars": str(sum(a.amount, Decimal(0))),
        "project_net_dollars": str(sum(p.project_amount, Decimal(0))),
        "historical_availability_verified": False,
        "national_model_ready": False,
        "limitations": ["Current revised extracts are not historical publication snapshots",
                        "Project totals are obligations, not payments or unmet need",
                        "County attribution, price conversion and loss linkage require review"],
    }
    return joined, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disaster", required=True, type=int)
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/funding_evidence"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/funding_evidence"))
    args = parser.parse_args()
    a, a_pages = fetch(args.disaster, ACTIVITIES, args.raw_dir / str(args.disaster))
    p, p_pages = fetch(args.disaster, PROJECTS, args.raw_dir / str(args.disaster))
    result, summary = reconcile(a, p)
    summary.update(disaster_number=args.disaster, sources=a_pages + p_pages)
    destination = args.output_dir / str(args.disaster)
    destination.mkdir(parents=True, exist_ok=True)
    result.to_csv(destination / "project_reconciliation.csv", index=False)
    (destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "sources"}, indent=2))


if __name__ == "__main__":
    main()
