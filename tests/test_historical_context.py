import json

import pandas as pd
import pytest

from recoverylens.context import RANKS
from recoverylens.historical_context import audit_counties, main, normalize


def source():
    return pd.DataFrame({"FIPS": ["01001", "01003", "01005"], "ST": ["01"] * 3,
                         "LOCATION": ["Example"] * 3, "E_TOTPOP": ["100", "200", "-999"],
                         "M_TOTPOP": ["0", "10", "bad"],
                         **{r: ["0.5", "0.8", "-999"] for r in RANKS}}).astype("string")


def test_zero_moe_and_unavailable_date_are_not_certified():
    result = normalize(source())
    assert result.population_moe_reported.iloc[0] == 0
    assert pd.isna(result.population_moe.iloc[0])
    assert result.population_moe_status.iloc[0] == "published_zero_unreviewed"
    assert result.population_moe.iloc[1] == 10
    assert result.context_available_year.isna().all()
    assert not result.model_context_approved.any()
    assert not result.geography_reviewed.any()
    assert result.baseline_values_present.tolist() == [True, True, False]
    assert result.population_baseline_raw.iloc[2] == "-999"


@pytest.mark.parametrize("bad", ["", "bad", "inf", "-999", "1.1"])
def test_bad_rank_is_withheld(bad):
    data = source()
    data.loc[0, "RPL_THEMES"] = bad
    result = normalize(data)
    assert pd.isna(result.RPL_THEMES.iloc[0])
    assert not result.baseline_values_present.iloc[0]


@pytest.mark.parametrize("problem", ["duplicate", "short", "state", "missing_state"])
def test_bad_geography_fails(problem):
    data = source()
    if problem == "duplicate":
        data.loc[1, "FIPS"] = "01001"
    elif problem == "short":
        data.loc[0, "FIPS"] = "1001"
    elif problem == "state":
        data.loc[0, "ST"] = "37"
    else:
        data.loc[0, "ST"] = pd.NA
    with pytest.raises(ValueError):
        normalize(data)


def test_county_audit_keeps_unmatched_and_does_not_approve_boundaries():
    result, report = audit_counties(normalize(source()),
                                    pd.DataFrame({"county_fips": ["01001", "99999"]}))
    assert result.key_status.tolist() == ["matched", "missing_in_2016"]
    assert report["missing_counties"] == 1
    assert report["requested_zero_population_moe_count"] == 1
    assert report["model_context_approved"] is False
    assert not result.model_context_approved.any()
    assert not result.model_context_approved.isna().any()
    assert not result.baseline_values_present.iloc[1]


def test_cli_hashes_input_and_preserves_distinct_counties(tmp_path, monkeypatch):
    requested = tmp_path / "counties.csv"
    requested.write_text("county_fips\n01001\n01001\n99999\n")

    def acquire(url, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        if str(path).endswith(".csv"):
            source().to_csv(path, index=False)
        else:
            path.write_bytes(b"documentation fixture")
        return {"url": url, "sha256": "fixture"}

    monkeypatch.setattr("recoverylens.historical_context.acquire", acquire)
    monkeypatch.setattr("sys.argv", ["context", "--county-keys", str(requested),
                                    "--raw-dir", str(tmp_path / "raw"),
                                    "--output-dir", str(tmp_path / "out")])
    main()
    report = json.loads((tmp_path / "out/summary.json").read_text())
    assert report["requested_counties"] == 2
    assert report["matched_counties"] == 1
    assert len(report["requested_input_sha256"]) == 64
    assert len(report["sources"]) == 2
