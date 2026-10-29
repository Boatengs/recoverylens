from __future__ import annotations

import pandas as pd
import pytest

from recoverylens.modeling import indicators
from recoverylens.pilot_panel import county_losses

CPI = pd.DataFrame({"year": [2018, 2022], "cpi": [100.0, 120.0], "source_url": ["bls", "bls"]})


def review_rows():
    return pd.DataFrame({
        "event_id": [1, 2, 3, 4, 5],
        "disaster_number": [4393, 4393, 4393, 4393, 4487],
        "county_fips": ["37019", "37019", "37047", "37047", "37019"],
        "decision": ["supported", "rejected", "supported", "unresolved", "rejected"],
    })


def damage_rows():
    return pd.DataFrame({
        "event_id": [1, 2, 3, 4, 5], "event_year": [2018] * 5,
        "known_total_damage_dollars": [1000.0, 50.0, 200.0, 70.0, 10.0],
        "is_damage_complete": [True, True, False, True, True],
    })


def test_losses_use_supported_links_only_and_price_by_event_year():
    out = county_losses(review_rows(), damage_rows(), CPI).set_index("county_fips")
    assert out.loc["37019", "loss_nominal"] == 1000.0
    assert out.loc["37019", "loss_dollars"] == pytest.approx(1200.0)
    assert out.loc["37019", "rejected_links"] == 1
    assert out.loc["37047", "unresolved_links"] == 1
    assert not out.loc["37047", "supported_complete"]


def test_competing_declaration_links_are_not_pilot_losses():
    out = county_losses(review_rows(), damage_rows(), CPI)
    assert set(out.disaster_number) == {4393}


def panel_row(**overrides):
    row = {
        "county_fips": "37019", "year": 2018, "population": 1000, "population_moe": 0,
        "population_moe_status": "controlled", "svi": 0.5, "funding_dollars": 100.0,
        "loss_dollars": 50.0, "price_base_year": 2022, "linkage_reviewed": True,
        "context_reference_year": 2016, "geography_reviewed": True, "funding_complete": True,
        "loss_complete": True, "source_reference": "test",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_retrospective_mode_uses_reference_year_not_release_year():
    out = indicators(panel_row(), mode="retrospective")
    assert out.model_eligible.item()
    assert out.analysis_mode.item() == "retrospective"


def test_retrospective_mode_still_rejects_later_context():
    out = indicators(panel_row(context_reference_year=2019), mode="retrospective")
    assert not out.model_eligible.item()
    assert "future_or_unknown_context" in out.exclusion_reasons.item()


def test_forecast_mode_still_requires_release_year():
    with pytest.raises(ValueError, match="context_available_year"):
        indicators(panel_row())


def test_unknown_mode_rejected():
    with pytest.raises(ValueError, match="mode"):
        indicators(panel_row(), mode="nowcast")
