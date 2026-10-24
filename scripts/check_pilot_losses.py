"""Assess, but never approve, 2018–2020 North Carolina pilot loss candidates."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from recoverylens.fema import build_session
from recoverylens.noaa import verified_storm_events_files
from recoverylens.storm_damage import analyze_storm_event_damage, read_storm_event_details
from recoverylens.storm_matching import (
    assess_event_declaration_candidates,
    read_storm_event_matching_details,
)

PILOT = [4393, 4465, 4543]


def main():
    files = verified_storm_events_files(
        "data/raw/noaa/storm-events", dataset="details", start_year=2018, end_year=2020)
    raw = read_storm_event_matching_details(files)
    # Include all NC declaration competitors, not just the three target disasters.
    query = ("state eq 'NC' and declarationType eq 'DR' and "
             "incidentBeginDate le '2020-12-31T23:59:59.999Z' and "
             "(incidentEndDate ge '2018-01-01T00:00:00.000Z' or incidentEndDate eq null)")
    response = build_session().get(
        "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries",
        params={"$filter": query, "$top": 1000, "$orderby": "disasterNumber"}, timeout=60)
    response.raise_for_status()
    declarations = response.json()["DisasterDeclarationsSummaries"]
    if len(declarations) >= 1000:
        raise ValueError("Declaration cap reached; pilot audit cannot proceed")
    root = Path("data/raw/pilot_losses")
    root.mkdir(parents=True, exist_ok=True)
    (root / "declarations.json").write_bytes(response.content)
    result = assess_event_declaration_candidates(raw, declarations)
    candidates = result.candidates.loc[result.candidates.disaster_number.isin(PILOT)].copy()
    damage = analyze_storm_event_damage(read_storm_event_details(files)).events
    if damage.event_id.isna().any() or damage.event_id.duplicated().any():
        raise ValueError("NOAA event identity is ambiguous")
    candidates = candidates.merge(damage[["event_id", "is_damage_complete",
                                         "known_total_damage_dollars"]],
                                  on="event_id", how="left", validate="many_to_one")
    rows = []
    for number in PILOT:
        part = candidates.loc[candidates.disaster_number.eq(number)]
        rows.append({"disaster_number": number, "candidate_rows": len(part),
                     "candidate_counties": int(part.county_fips.nunique()),
                     "complete_damage_candidates": int(part.is_damage_complete.sum()),
                     "ambiguous_candidates": int(part.candidate_count.gt(1).sum()),
                     "confirmed_links": 0})
    destination = Path("data/processed/pilot_losses")
    destination.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(destination / "candidate_review.csv", index=False)
    report = {"status": "review_required", "pilot": rows,
              "declaration_rows": len(declarations), "sources": {
                  "declarations_url": response.url,
                  "retrieved_at": datetime.now(UTC).isoformat(),
                  "declarations_sha256": hashlib.sha256(response.content).hexdigest(),
                  "noaa": [f.manifest_record for f in files]},
              "limitation": "County/date candidates are not reviewed causal links"}
    (destination / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
