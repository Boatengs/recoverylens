from __future__ import annotations

import hashlib
import json
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from recoverylens.context import RANKS, acquire, integrate, read_acs, require_keys
from recoverylens.modeling import adjust_dollars, evaluate, indicators


def panel():
    rows = []
    for year in (2018, 2019, 2020):
        for i in range(12):
            rows.append({"county_fips": f"01{i + 1:03d}", "year": year,
                         "population": 1000 + i * 200, "population_moe": 20,
                         "svi": i / 12, "funding_dollars": 5000 + i * 1000 + (year-2018)*200,
                         "loss_dollars": 10000 + i * 500, "price_base_year": 2022,
                         "linkage_reviewed": True, "geography_reviewed": True,
                         "funding_complete": True, "loss_complete": True,
                         "context_available_year": 2017, "source_reference": "synthetic-test"})
    return pd.DataFrame(rows)


def test_bulk_counties_and_uncertainty(tmp_path):
    p = tmp_path / "population.dat"
    p.write_text("GEO_ID|B01003_E001|B01003_M001\n"
                 "0100000US|1000000|0\n0500000US01001|1000|-555555555\n"
                 "0500000US01003|-999999999|10\n", encoding="utf-8")
    result = read_acs(p, "b01003", 2022)
    assert result.county_fips.tolist() == ["01001", "01003"]
    assert pd.isna(result.loc[0, "population_moe"])
    assert result.loc[0, "population_moe_raw"] == "-555555555"
    assert result.loc[0, "population_moe_status"] == "controlled"
    assert pd.isna(result.loc[1, "population_estimate"])


def test_context_preserves_unmatched_and_missing_rank():
    acs = pd.DataFrame({"county_fips": ["01001", "72001"], "population_estimate": [1000, 500]})
    svi = pd.DataFrame({"FIPS": ["01001"], "LOCATION": ["Example"],
                        **{c: ["-999"] for c in RANKS}})
    joined, audit, report = integrate(acs, svi, year=2022)
    assert len(joined) == 2 and len(audit) == 2
    assert joined.geography_status.tolist() == ["matched", "acs_only"]
    assert joined.RPL_THEMES.isna().all()
    assert report["ready_count"] == 0
    with pytest.raises(ValueError):
        integrate(acs, svi, year=2020)


def test_duplicate_geography_is_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        require_keys(pd.DataFrame({"county_fips": ["01001", "01001"]}), "county_fips")


def test_cpi_retains_nominal_missingness_and_negative_adjustments():
    cpi = pd.DataFrame({"year": [2020, 2022], "cpi": [100, 120],
                        "source_url": ["https://www.bls.gov", "https://www.bls.gov"]})
    result = adjust_dollars(pd.Series([100, None, -10, 20]),
                            pd.Series([2020, 2020, 2020, 2019]), cpi, 2022)
    assert result.adjusted_dollars.iloc[0] == 120
    assert result.adjusted_dollars.iloc[2] == -12
    assert result.adjusted_dollars.isna().sum() == 2
    with pytest.raises(ValueError):
        adjust_dollars(pd.Series([100]), pd.Series([2020]), cpi, 2021)


def test_indicators_withhold_unreviewed_and_future_context():
    data = panel()
    data.loc[0, "linkage_reviewed"] = False
    data.loc[1, "context_available_year"] = 2025
    data.loc[2, "loss_dollars"] = 0
    result = indicators(data)
    assert result.model_eligible.sum() == len(data) - 3
    assert result.funding_to_loss.iloc[:3].isna().all()
    assert "future_or_unknown_context" in result.exclusion_reasons.iloc[1]


def test_zero_population_lower_bound_does_not_produce_infinity():
    data = panel()
    data.loc[0, "population_moe"] = data.loc[0, "population"]
    result = indicators(data)
    assert pd.isna(result.funding_per_resident_high.iloc[0])


def test_controlled_population_supports_point_estimate_without_fake_interval():
    data = panel()
    data.loc[0, "population_moe"] = np.nan
    data["population_moe_status"] = "observed"
    data.loc[0, "population_moe_status"] = "controlled"
    result = indicators(data)
    assert result.model_eligible.iloc[0]
    assert pd.isna(result.funding_per_resident_low.iloc[0])


def test_temporal_evaluation_is_deterministic_and_retains_exclusions():
    data = panel()
    data.loc[35, "svi"] = -999
    result, sensitivity, report = evaluate(data, holdout_year=2020)
    shuffled, _, other = evaluate(data.sample(frac=1, random_state=1), holdout_year=2020)
    pd.testing.assert_frame_equal(result, shuffled)
    assert report == other
    assert report["training_rows"] == 24 and report["holdout_rows"] == 11
    assert report["excluded_rows"] == 1
    assert result.typology.iloc[-1] is pd.NA
    assert len(sensitivity) == 3


def test_holdout_targets_cannot_change_training_or_predictions():
    data = panel()
    first, _, report = evaluate(data, holdout_year=2020)
    data.loc[data.year.eq(2020), "funding_dollars"] *= 100
    second, _, changed = evaluate(data, holdout_year=2020)
    np.testing.assert_allclose(first.predicted_funding_per_resident,
                               second.predicted_funding_per_resident)
    assert report["ridge_coefficients"] == changed["ridge_coefficients"]
    assert report["cluster_centers_standardized"] == changed["cluster_centers_standardized"]


def test_insufficient_history_and_mixed_price_bases_fail():
    with pytest.raises(ValueError, match="training"):
        evaluate(panel().query("year == 2020"), holdout_year=2020)
    data = panel()
    data.loc[0, "price_base_year"] = 2020
    with pytest.raises(ValueError, match="common price"):
        indicators(data)


def test_normalized_duplicate_years_fail():
    data = panel().astype({"year": "object"})
    duplicate = data.iloc[[0]].copy()
    duplicate["year"] = "2018"
    with pytest.raises(ValueError, match="Duplicate"):
        indicators(pd.concat([data, duplicate], ignore_index=True))


def test_fractional_context_year_fails():
    data = panel().astype({"context_available_year": "float64"})
    data.loc[0, "context_available_year"] = 2017.5
    with pytest.raises(ValueError, match="integer years"):
        indicators(data)


@pytest.mark.parametrize("content_type,payload,valid", [
    ("text/csv", b"county,value\n01001,1\n", True),
    ("text/html", b"<html>error</html>", False),
    ("text/csv", b"", False),
])
def test_acquisition_preserves_existing_file_on_failure(
        tmp_path, monkeypatch, content_type, payload, valid):
    session = MagicMock()
    response = session.get.return_value.__enter__.return_value
    response.headers = {"Content-Type": content_type}
    response.iter_content.return_value = [payload]
    monkeypatch.setattr("recoverylens.context.build_session", lambda: session)
    target = tmp_path / "source.csv"
    target.write_bytes(b"previous")
    if valid:
        manifest = acquire("https://example.test/source", target)
        assert manifest["sha256"] == hashlib.sha256(payload).hexdigest()
        assert manifest["bytes"] == len(payload)
        assert target.read_bytes() == payload
    else:
        with pytest.raises(ValueError):
            acquire("https://example.test/source", target)
        assert target.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [target]


def test_model_cli_writes_auditable_outputs(tmp_path, monkeypatch):
    from recoverylens.modeling import main

    source = tmp_path / "panel.csv"
    panel().to_csv(source, index=False)
    output = tmp_path / "output"
    monkeypatch.setattr("sys.argv", ["modeling", "--panel", str(source),
                                    "--holdout-year", "2020", "--output-dir", str(output)])
    main()
    report = json.loads((output / "model_report.json").read_text())
    assert report["input_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert report["training_rows"] == 24
    assert len(pd.read_csv(output / "county_analysis.csv")) == 36
    assert len(pd.read_csv(output / "sensitivity.csv")) == 3
