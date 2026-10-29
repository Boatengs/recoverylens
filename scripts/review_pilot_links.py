"""Replay the documented episode review against pinned NOAA/FEMA snapshots."""

import hashlib
import json
from pathlib import Path

import pandas as pd

from recoverylens.link_review import EVIDENCE, KEYS, apply_review
from recoverylens.noaa import verified_storm_events_files
from recoverylens.storm_matching import (
    assess_event_declaration_candidates,
    read_storm_event_matching_details,
)


def main():
    rules = json.loads(Path("docs/reviews/pilot-episodes.json").read_text())
    declarations_path = Path("data/raw/pilot_losses/declarations.json")
    declaration_hash = hashlib.sha256(declarations_path.read_bytes()).hexdigest()
    files = verified_storm_events_files(
        "data/raw/noaa/storm-events", dataset="details", start_year=2018, end_year=2020)
    current_noaa = {f.source.data_year: f.manifest_record["sha256"] for f in files}
    pinned = (declaration_hash == rules["declarations_sha256"]
              and current_noaa == {int(k): v for k, v in rules["noaa_sha256"].items()})
    if not pinned and "expected_counts" not in rules:
        raise ValueError("Snapshots changed and the ledger has no content check; repeat review")
    declarations = json.loads(declarations_path.read_text())["DisasterDeclarationsSummaries"]
    assessment = assess_event_declaration_candidates(
        read_storm_event_matching_details(files), declarations)
    all_links = assessment.candidates
    ids = set(all_links.loc[all_links.disaster_number.isin([4393, 4465, 4543]), "event_id"])
    candidates = all_links.loc[all_links.event_id.isin(ids)].copy()
    narratives = []
    for source in files:
        table = pd.read_csv(source.path, usecols=["EVENT_ID", "EPISODE_NARRATIVE"],
                            keep_default_na=False)
        table = table.loc[table.EVENT_ID.isin(ids)].copy()
        table["noaa_sha256"] = source.manifest_record["sha256"]
        table["narrative_sha256"] = table.EPISODE_NARRATIVE.map(
            lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest())
        narratives.append(table.rename(columns={"EVENT_ID": "event_id"}))
    candidates = candidates.merge(pd.concat(narratives), on="event_id", validate="many_to_one")
    candidates["declarations_sha256"] = declaration_hash
    ledger = []
    episode_rules = {(r["disaster_number"], r["episode_id"]): r for r in rules["episodes"]}
    for _, row in candidates.iterrows():
        key = (int(row.disaster_number), int(row.episode_id))
        if key in episode_rules:
            rule = episode_rules[key]
            if row.narrative_sha256 != rule["narrative_sha256"]:
                raise ValueError("Narrative changed; repeat review")
            decision, reason = rule["decision"], rule["reason"]
        elif row.disaster_number == 4487 and row.incident_type == "Biological":
            decision = "rejected"
            reason = "Weather-event attribution to COVID-19 is unsupported; hazard mismatch"
        else:
            decision, reason = "unresolved", "Competing declaration needs documentary review"
        ledger.append({**{k: row[k] for k in [*KEYS, *EVIDENCE]},
                       "decision": decision, "reason": reason,
                       "reviewer": rules["reviewer"], "review_date": rules["review_date"]})
    reviewed = apply_review(candidates, pd.DataFrame(ledger))
    counts = reviewed.groupby(["disaster_number", "decision"]).size()
    observed = {f"{k[0]}:{k[1]}": int(v) for k, v in counts.items()}
    if not pinned:
        # Content check: every reviewed narrative hash already matched above. The link
        # set must also reproduce the reviewed decision counts exactly, with no episode
        # outside the ledger, or the decisions are not carried over.
        unknown = [
            key for key in {(int(r.disaster_number), int(r.episode_id))
                            for r in candidates.itertuples()}
            if key not in episode_rules and key[0] != 4487
        ]
        if unknown or observed != rules["expected_counts"]:
            raise ValueError(
                f"Candidate links differ from the reviewed set; repeat review. "
                f"observed={observed} unknown_episodes={sorted(unknown)[:10]}")
    destination = Path("data/processed/pilot_link_review")
    destination.mkdir(parents=True, exist_ok=True)
    reviewed.to_csv(destination / "documentary_review.csv", index=False)
    summary = {"review_date": rules["review_date"],
               "replay_basis": "pinned_snapshots" if pinned else "content_verified",
               "current_sources": {"declarations_sha256": declaration_hash,
                                   "noaa_sha256": {str(k): v for k, v in current_noaa.items()}},
               "counts": [{"disaster_number": int(k[0]), "decision": k[1], "rows": int(v)}
                          for k, v in counts.items()],
               "rules_sha256": hashlib.sha256(
                   Path("docs/reviews/pilot-episodes.json").read_bytes()).hexdigest(),
               "model_linkage_approved": False, "national_model_ready": False}
    (destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
