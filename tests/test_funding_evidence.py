from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd
import pytest

from recoverylens.funding_evidence import ACTIVITIES, fetch, money, reconcile


def sources():
    common = {"disasterNumber": 4393, "applicantId": "001-EXAMPLE", "pwNumber": 1}
    a = pd.DataFrame([
        {**common, "id": "a", "federalShareObligated": "100.10",
         "dateObligated": "2018-10-01", "fundingStatus": "O", "versionNumber": 0},
        {**common, "id": "b", "federalShareObligated": "-20.05",
         "dateObligated": "2019-10-01", "fundingStatus": "O", "versionNumber": 1},
    ])
    p = pd.DataFrame([{**common, "federalShareObligated": "80.05"}])
    return a, p


def test_exact_cent_reconciliation_preserves_deobligations():
    a, p = sources()
    result, report = reconcile(a, p)
    assert result.activity_amount.iloc[0] == Decimal("80.05")
    assert report["reconciled_projects"] == 1
    assert report["negative_activity_count"] == 1
    assert report["activity_net_dollars"] == "80.05"
    assert report["national_model_ready"] is False
    assert report["historical_availability_verified"] is False


@pytest.mark.parametrize("field,value", [("dateObligated", "bad"), ("fundingStatus", "N")])
def test_balanced_but_unsupported_activity_is_not_ready(field, value):
    a, p = sources()
    a.loc[0, field] = value
    result, report = reconcile(a, p)
    assert result.reconciled.iloc[0]
    assert report["dated_funding_candidate_projects"] == 0


def test_unmatched_and_unbalanced_projects_remain_visible():
    a, p = sources()
    p.loc[0, "federalShareObligated"] = "80.06"
    p.loc[1] = [4393, "002-EXAMPLE", 2, "50.00"]
    result, report = reconcile(a, p)
    assert len(result) == 2
    assert report["unreconciled_projects"] == 2
    assert not result.dated_funding_candidate.any()


@pytest.mark.parametrize("problem", ["activity_duplicate", "project_duplicate", "missing_key"])
def test_ambiguous_identities_fail(problem):
    a, p = sources()
    if problem == "activity_duplicate":
        a.loc[1, "id"] = "a"
    elif problem == "project_duplicate":
        p = pd.concat([p, p])
    else:
        a.loc[0, "applicantId"] = ""
    with pytest.raises(ValueError):
        reconcile(a, p)


@pytest.mark.parametrize("value", [None, "bad", "NaN", "Infinity", "1.001"])
def test_invalid_money_is_not_silently_coerced(value):
    with pytest.raises(ValueError):
        money(value)


def test_fetch_requires_evidence_beyond_full_page(tmp_path, monkeypatch):
    session = MagicMock()
    response = MagicMock()
    response.json.return_value = {ACTIVITIES: [{"id": str(i)} for i in range(1000)]}
    response.content = b"test response"
    response.url = "https://www.fema.gov/api/open/v2/test"
    session.get.return_value = response
    monkeypatch.setattr("recoverylens.funding_evidence.build_session", lambda: session)
    with pytest.raises(ValueError, match="cap"):
        fetch(4393, ACTIVITIES, tmp_path, limit=1000)
    assert session.get.call_count == 2


def test_fetch_records_exact_response_hash(tmp_path, monkeypatch):
    import hashlib

    session = MagicMock()
    response = session.get.return_value
    response.json.return_value = {ACTIVITIES: [{"id": "a"}]}
    response.content = b'{"example":1}'
    response.url = "https://www.fema.gov/api/open/v2/test"
    monkeypatch.setattr("recoverylens.funding_evidence.build_session", lambda: session)
    result, manifest = fetch(4393, ACTIVITIES, tmp_path)
    assert len(result) == 1
    assert manifest[0]["sha256"] == hashlib.sha256(response.content).hexdigest()
    assert (tmp_path / manifest[0]["filename"]).read_bytes() == response.content
