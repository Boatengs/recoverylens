"""Export NOAA episode narratives for pilot links that still lack a decision.

Writes one row per (declaration, episode) so a reviewer can read the source text
the ledger will be bound to. It records hashes and never makes a decision.
"""

import hashlib
import json
from pathlib import Path

import pandas as pd

from recoverylens.noaa import verified_storm_events_files

PILOT = [4393, 4465, 4543]
OUT = Path("docs/reviews/pending")


def main():
    rules = json.loads(Path("docs/reviews/pilot-episodes.json").read_text())
    decided = {(r["disaster_number"], r["episode_id"]): r["decision"] for r in rules["episodes"]}
    candidates = pd.read_csv("data/processed/pilot_losses/candidate_review.csv",
                             dtype={"county_fips": str})
    candidates = candidates.loc[candidates.disaster_number.isin(PILOT)]
    files = verified_storm_events_files(
        "data/raw/noaa/storm-events", dataset="details", start_year=2018, end_year=2020)
    text = pd.concat(
        pd.read_csv(f.path, usecols=["EVENT_ID", "EPISODE_ID", "EPISODE_NARRATIVE",
                                     "EVENT_NARRATIVE"], keep_default_na=False)
        for f in files).rename(columns={"EVENT_ID": "event_id", "EPISODE_ID": "episode_id"})
    rows = []
    for (disaster, episode), part in candidates.groupby(["disaster_number", "episode_id"]):
        status = decided.get((int(disaster), int(episode)), "not in ledger")
        if status == "supported":
            continue
        narr = text.loc[text.event_id.isin(part.event_id)]
        episode_text = narr.EPISODE_NARRATIVE.drop_duplicates()
        rows.append({
            "disaster_number": int(disaster), "episode_id": int(episode),
            "ledger_status": status, "links": len(part),
            "event_types": ";".join(sorted(part.event_type.dropna().unique())),
            "first_event_begin": str(part.event_begin_date.min()),
            "last_event_end": str(part.event_end_date.max()),
            "counties": ";".join(sorted(part.cz_name.dropna().unique())),
            "incident_begin": str(part.incident_begin_date.iloc[0]),
            "incident_end": str(part.incident_end_date.iloc[0]),
            "distinct_episode_narratives": int(episode_text.size),
            "narrative_sha256": ";".join(
                hashlib.sha256(t.encode("utf-8")).hexdigest() for t in episode_text),
            "episode_narrative": " || ".join(episode_text),
            "event_narratives": " || ".join(narr.EVENT_NARRATIVE.drop_duplicates().head(12)),
        })
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT / "undecided_episodes.csv", index=False)
    print(f"{len(rows)} undecided episodes written")


if __name__ == "__main__":
    main()
