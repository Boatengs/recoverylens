import numpy as np
import pandas as pd
import pytest

from recoverylens.metrics import EquityWeights, calculate_equity_score, percentile_rank


def test_percentile_rank_preserves_missing_values():
    ranked = percentile_rank(pd.Series([10, 20, np.nan, 30]))
    assert ranked.iloc[0] == pytest.approx(1 / 3)
    assert ranked.iloc[2] is np.nan or np.isnan(ranked.iloc[2])
    assert ranked.iloc[3] == 1


def test_equity_score_is_higher_for_greater_unmet_need():
    counties = pd.DataFrame(
        {
            "county_fips": ["00001", "00002", "00003"],
            "declaration_rate": [1, 2, 3],
            "loss_per_capita": [10, 20, 30],
            "svi": [0.1, 0.5, 0.9],
            "funding_gap": [0.2, 0.4, 0.8],
        }
    )
    result = calculate_equity_score(counties)
    assert result["equity_score"].is_monotonic_increasing
    assert result.loc[2, "equity_score"] == pytest.approx(100)


def test_score_is_withheld_when_required_components_are_missing():
    counties = pd.DataFrame(
        {
            "declaration_rate": [1],
            "loss_per_capita": [10],
            "svi": [0.4],
            "funding_gap": [np.nan],
        }
    )
    result = calculate_equity_score(counties)
    assert np.isnan(result.loc[0, "equity_score"])
    assert result.loc[0, "components_observed"] == 3


def test_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        EquityWeights(exposure=0.5)
