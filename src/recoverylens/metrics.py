"""Transparent county-level metrics used by RecoveryLens."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class EquityWeights:
    """Weights for the four published recovery-equity components."""

    exposure: float = 0.25
    loss: float = 0.25
    vulnerability: float = 0.25
    funding_gap: float = 0.25

    def __post_init__(self) -> None:
        values = (self.exposure, self.loss, self.vulnerability, self.funding_gap)
        if any(value < 0 for value in values):
            raise ValueError("weights cannot be negative")
        if not np.isclose(sum(values), 1.0):
            raise ValueError("weights must sum to 1.0")


def percentile_rank(series: pd.Series) -> pd.Series:
    """Rank observed values to [0, 1] while preserving missingness."""

    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.rank(method="average", pct=True, na_option="keep")


def calculate_equity_score(
    counties: pd.DataFrame,
    *,
    weights: EquityWeights | None = None,
    minimum_components: int = 4,
) -> pd.DataFrame:
    """Calculate a transparent priority score without imputing missing inputs.

    Required inputs are ``declaration_rate``, ``loss_per_capita``, ``svi`` and
    ``funding_gap``. Higher values always indicate greater potential unmet need.
    Scores are withheld when fewer than ``minimum_components`` are observed.
    """

    weights = weights or EquityWeights()
    source_columns = {
        "exposure": "declaration_rate",
        "loss": "loss_per_capita",
        "vulnerability": "svi",
        "funding_gap": "funding_gap",
    }
    missing = sorted(set(source_columns.values()) - set(counties.columns))
    if missing:
        raise ValueError(f"Cannot calculate equity score; missing fields: {missing}")
    if minimum_components not in {1, 2, 3, 4}:
        raise ValueError("minimum_components must be between 1 and 4")

    result = counties.copy()
    component_weights = {
        "exposure": weights.exposure,
        "loss": weights.loss,
        "vulnerability": weights.vulnerability,
        "funding_gap": weights.funding_gap,
    }
    rank_columns: list[str] = []
    for component, source in source_columns.items():
        column = f"{component}_percentile"
        result[column] = percentile_rank(result[source])
        rank_columns.append(column)

    observed = result[rank_columns].notna()
    weighted_sum = sum(
        result[f"{component}_percentile"].fillna(0) * weight
        for component, weight in component_weights.items()
    )
    observed_weight = sum(
        observed[f"{component}_percentile"] * weight
        for component, weight in component_weights.items()
    )
    result["components_observed"] = observed.sum(axis=1)
    result["equity_score"] = (weighted_sum / observed_weight.replace(0, np.nan) * 100).where(
        result["components_observed"] >= minimum_components
    )
    return result
