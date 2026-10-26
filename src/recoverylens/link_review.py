"""Apply explicit documentary link decisions without approving a model panel."""

from __future__ import annotations

import pandas as pd

KEYS = ["event_id", "disaster_number"]
EVIDENCE = ["noaa_sha256", "declarations_sha256", "narrative_sha256"]
DECISIONS = {"supported", "rejected", "unresolved"}


def apply_review(candidates: pd.DataFrame, decisions: pd.DataFrame) -> pd.DataFrame:
    """Fail on stale evidence, unknown links, duplicate decisions or double allocation."""
    if not {*KEYS, *EVIDENCE}.issubset(candidates):
        raise ValueError("Candidates require link identity and evidence hashes")
    reserved = {"decision", "reason", "reviewer", "review_date", "_merge",
                "independent_review_complete", "model_linkage_approved",
                *[c + "_review" for c in EVIDENCE]}
    if reserved.intersection(candidates):
        raise ValueError("Supply raw candidates, not previously reviewed output")
    if not {*KEYS, *EVIDENCE, "decision", "reason", "reviewer", "review_date"}.issubset(decisions):
        raise ValueError("Review ledger is missing required fields")
    for frame in (candidates, decisions):
        if frame[KEYS].isna().any().any() or frame.duplicated(KEYS).any():
            raise ValueError("Missing or duplicate link identity")
        for column in EVIDENCE:
            if not frame[column].astype("string").str.fullmatch(r"[0-9a-f]{64}", na=False).all():
                raise ValueError("Invalid evidence hash")
    if not decisions.decision.isin(DECISIONS).all():
        raise ValueError("Unknown review decision")
    for column in ("reason", "reviewer", "review_date"):
        if decisions[column].fillna("").astype(str).str.strip().eq("").any():
            raise ValueError("Review attribution and reasoning must be present")
    if pd.to_datetime(decisions.review_date, format="%Y-%m-%d", errors="coerce").isna().any():
        raise ValueError("Invalid review date")
    joined = candidates.merge(decisions, on=KEYS, how="outer", validate="one_to_one",
                              suffixes=("", "_review"), indicator=True)
    if joined._merge.eq("right_only").any():
        raise ValueError("Review refers to a nonexistent candidate")
    reviewed = joined._merge.eq("both")
    for column in EVIDENCE:
        if not joined.loc[reviewed, column].eq(joined.loc[reviewed, column + "_review"]).all():
            raise ValueError("Source changed; documentary review must be repeated")
    joined["decision"] = joined.decision.fillna("unresolved")
    joined["reason"] = joined.reason.fillna("No documentary decision recorded")
    supported = joined.loc[joined.decision.eq("supported")]
    if supported.event_id.duplicated().any():
        raise ValueError("One event cannot support multiple disaster allocations")
    joined["independent_review_complete"] = False
    joined["model_linkage_approved"] = False
    return joined.drop(columns=["_merge", *[c + "_review" for c in EVIDENCE]])
