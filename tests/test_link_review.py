import pandas as pd
import pytest

from recoverylens.link_review import apply_review


def inputs():
    candidates = pd.DataFrame({"event_id": [1, 1, 2], "disaster_number": [4543, 4487, 4543],
                               "noaa_sha256": ["a" * 64] * 3,
                               "declarations_sha256": ["b" * 64] * 3,
                               "narrative_sha256": ["c" * 64] * 3})
    decisions = candidates.iloc[:2].copy()
    decisions["decision"] = ["supported", "rejected"]
    decisions["reason"] = ["Documentary support", "Biological hazard mismatch"]
    decisions["reviewer"] = "test reviewer"
    decisions["review_date"] = "2026-10-26"
    return candidates, decisions


def test_documentary_support_never_approves_panel_and_preserves_unreviewed():
    candidates, decisions = inputs()
    result = apply_review(candidates, decisions)
    assert set(result.decision) == {"supported", "rejected", "unresolved"}
    assert not result.model_linkage_approved.any()
    assert not result.independent_review_complete.any()


@pytest.mark.parametrize("field", ["noaa_sha256", "declarations_sha256", "narrative_sha256"])
def test_stale_review_rejected(field):
    candidates, decisions = inputs()
    decisions.loc[0, field] = "d" * 64
    with pytest.raises(ValueError, match="Source changed"):
        apply_review(candidates, decisions)


def test_event_cannot_be_allocated_to_two_supported_disasters():
    candidates, decisions = inputs()
    decisions["decision"] = "supported"
    with pytest.raises(ValueError, match="multiple disaster"):
        apply_review(candidates, decisions)


def test_nonexistent_review_candidate_fails():
    candidates, decisions = inputs()
    decisions.loc[0, "event_id"] = 99
    with pytest.raises(ValueError, match="nonexistent"):
        apply_review(candidates, decisions)


def test_old_decisions_cannot_override_new_ledger():
    candidates, decisions = inputs()
    previous = apply_review(candidates, decisions)
    decisions.loc[0, "decision"] = "rejected"
    with pytest.raises(ValueError, match="raw candidates"):
        apply_review(previous, decisions)


@pytest.mark.parametrize("problem", ["duplicate", "blank_reason", "bad_date", "bad_hash"])
def test_invalid_review_evidence_fails(problem):
    candidates, decisions = inputs()
    if problem == "duplicate":
        decisions = pd.concat([decisions, decisions.iloc[[0]]])
    elif problem == "blank_reason":
        decisions.loc[0, "reason"] = " "
    elif problem == "bad_date":
        decisions.loc[0, "review_date"] = "unknown"
    else:
        decisions.loc[0, "noaa_sha256"] = "unknown"
    with pytest.raises(ValueError):
        apply_review(candidates, decisions)
