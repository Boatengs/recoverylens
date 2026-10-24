"""Chronological, review-gated county indicators and exploratory models."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

FEATURES = ["log_population", "log_loss_per_resident", "svi"]
REQUIRED = {
    "county_fips", "year", "population", "population_moe", "svi", "funding_dollars",
    "loss_dollars", "price_base_year", "linkage_reviewed", "context_available_year",
    "geography_reviewed", "funding_complete", "loss_complete", "source_reference",
}


def adjust_dollars(values: pd.Series, years: pd.Series, cpi: pd.DataFrame,
                   base_year: int) -> pd.DataFrame:
    """Convert nominal values with supplied annual CPI-U indexes; preserve nulls."""
    if not {"year", "cpi", "source_url"}.issubset(cpi):
        raise ValueError("CPI requires year, cpi, and source_url")
    index = cpi.copy()
    index["year"] = pd.to_numeric(index.year, errors="raise")
    index["cpi"] = pd.to_numeric(index.cpi, errors="raise")
    if (index.year.duplicated().any() or index.year.isna().any()
            or not index.year.mod(1).eq(0).all() or not index.cpi.gt(0).all()
            or not np.isfinite(index.cpi).all()
            or index.source_url.fillna("").str.strip().eq("").any()):
        raise ValueError("Invalid or duplicate annual CPI observations")
    series = index.set_index("year").cpi
    if base_year not in series:
        raise ValueError("CPI base year is unavailable")
    nominal = pd.to_numeric(values, errors="coerce").where(lambda x: np.isfinite(x))
    price = pd.to_numeric(years, errors="coerce").map(series)
    return pd.DataFrame({"nominal_dollars": nominal, "price_base_year": base_year,
                         "cpi_factor": series.loc[base_year] / price,
                         "adjusted_dollars": nominal * series.loc[base_year] / price})


def indicators(panel: pd.DataFrame) -> pd.DataFrame:
    """Retain every input row and disclose reasons for withholding model inputs."""
    missing = REQUIRED - set(panel)
    if missing:
        raise ValueError(f"Missing panel fields: {sorted(missing)}")
    out = panel.copy().reset_index(drop=True)
    if (not out.county_fips.astype("string").str.fullmatch(r"\d{5}", na=False).all()
            or out.duplicated(["county_fips", "year"]).any()):
        raise ValueError("Invalid or duplicate county-year keys")
    numeric = ["year", "population", "population_moe", "svi", "funding_dollars",
               "loss_dollars", "price_base_year", "context_available_year"]
    for col in numeric:
        out[col] = pd.to_numeric(out[col], errors="coerce").where(lambda x: np.isfinite(x))
    if out.year.isna().any() or not out.year.mod(1).eq(0).all():
        raise ValueError("Year must be a finite integer")
    if out.duplicated(["county_fips", "year"]).any():
        raise ValueError("Duplicate county-year keys after numeric normalization")
    for col in ("price_base_year", "context_available_year"):
        if not out[col].dropna().mod(1).eq(0).all():
            raise ValueError(f"{col} must contain integer years")
    if out.price_base_year.dropna().nunique() != 1:
        raise ValueError("All rows must use one common price base year")
    controlled = out.get("population_moe_status", pd.Series("observed", index=out.index)).eq(
        "controlled")
    gates = {
        "population_unavailable": ~out.population.gt(0),
        "population_uncertainty_unavailable": ~(out.population_moe.ge(0) | controlled),
        "svi_unavailable": ~out.svi.between(0, 1),
        "funding_unavailable_or_negative": ~out.funding_dollars.ge(0),
        "loss_unavailable_or_zero": ~out.loss_dollars.gt(0),
        "price_base_unavailable": out.price_base_year.isna(),
        "future_or_unknown_context": ~out.context_available_year.le(out.year),
        "source_reference_missing": out.source_reference.fillna("").str.strip().eq(""),
    }
    for col in ("linkage_reviewed", "geography_reviewed", "funding_complete", "loss_complete"):
        gates[col + "_not_confirmed"] = ~out[col].astype("string").str.lower().eq("true")
    flags = pd.DataFrame(gates).fillna(True)
    out["exclusion_reasons"] = flags.apply(
        lambda row: ";".join(row.index[row]), axis=1)
    out["model_eligible"] = ~flags.any(axis=1)
    ready = out.model_eligible
    out["funding_per_resident"] = (out.funding_dollars / out.population).where(ready)
    out["funding_to_loss"] = (out.funding_dollars / out.loss_dollars).where(ready)
    # Denominator sensitivity interval only; not an overall funding confidence interval.
    out["funding_per_resident_low"] = (
        out.funding_dollars / (out.population + out.population_moe)).where(ready)
    out["funding_per_resident_high"] = (
        out.funding_dollars / (out.population - out.population_moe)
    ).where(ready & out.population.gt(out.population_moe))
    out["log_population"] = np.log1p(out.population.where(ready))
    out["log_loss_per_resident"] = np.log1p((out.loss_dollars / out.population).where(ready))
    return out.sort_values(["year", "county_fips"]).reset_index(drop=True)


def _ridge(x: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    design = np.column_stack([np.ones(len(x)), x])
    penalty = np.eye(design.shape[1]) * alpha
    penalty[0, 0] = 0
    return np.linalg.solve(design.T @ design + penalty, design.T @ y)


def _clusters(x: np.ndarray, k: int) -> tuple:
    """Deterministic farthest-point initialization, followed by Lloyd iterations."""
    if len(np.unique(x, axis=0)) < k:
        raise ValueError("Fewer distinct training observations than clusters")
    centers = [x[0]]
    while len(centers) < k:
        distances = ((x[:, None, :] - np.array(centers)) ** 2).sum(axis=2).min(axis=1)
        centers.append(x[int(distances.argmax())])
    centers = np.array(centers)
    for _ in range(100):
        labels = ((x[:, None, :] - centers) ** 2).sum(axis=2).argmin(axis=1)
        updated = np.array([x[labels == i].mean(axis=0) if (labels == i).any()
                            else centers[i] for i in range(k)])
        if np.allclose(updated, centers, rtol=0, atol=1e-10):
            return updated, True
        centers = updated
    return centers, False


def evaluate(panel: pd.DataFrame, *, holdout_year: int, clusters: int = 3) -> tuple:
    """Fit only earlier years; publish holdout errors and fixed-parameter sensitivity."""
    out = indicators(panel)
    train = out.model_eligible & out.year.lt(holdout_year)
    test = out.model_eligible & out.year.ge(holdout_year)
    if train.sum() < 20 or test.sum() < 5 or out.loc[train, "year"].nunique() < 2:
        raise ValueError("Need >=20 training rows across >=2 years and >=5 holdout rows")
    if not 2 <= clusters <= 8:
        raise ValueError("clusters must be between 2 and 8")
    x = out.loc[train, FEATURES].to_numpy(dtype=float)
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale == 0] = 1
    x = (x - mean) / scale
    all_x = (out.loc[out.model_eligible, FEATURES].to_numpy(dtype=float) - mean) / scale
    test_x = (out.loc[test, FEATURES].to_numpy(dtype=float) - mean) / scale
    y = np.log1p(out.loc[train, "funding_per_resident"].to_numpy(dtype=float))
    test_y = out.loc[test, "funding_per_resident"].to_numpy(dtype=float)
    rows, predictions = [], {}
    for alpha in (0.1, 1.0, 10.0):
        beta = _ridge(x, y, alpha)
        prediction = np.maximum(np.expm1(np.clip(
            np.column_stack([np.ones(len(test_x)), test_x]) @ beta, -30, 30)), 0)
        error = prediction - test_y
        rows.append({"ridge_alpha": alpha, "holdout_mae": float(np.abs(error).mean()),
                     "holdout_rmse": float(np.sqrt((error ** 2).mean()))})
        predictions[alpha] = prediction
        if alpha == 1:
            fitted_beta = beta
    baseline = float(out.loc[train, "funding_per_resident"].median())
    fitted = np.column_stack([np.ones(len(all_x)), all_x]) @ fitted_beta
    out["predicted_funding_per_resident"] = np.nan
    out.loc[out.model_eligible, "predicted_funding_per_resident"] = np.maximum(
        np.expm1(np.clip(fitted, -30, 30)), 0)
    out["funding_residual_per_resident"] = (
        out.funding_per_resident - out.predicted_funding_per_resident)
    train_residual = out.loc[train, "funding_residual_per_resident"]
    center = float(train_residual.median())
    mad = float((train_residual - center).abs().median())
    out["residual_outlier"] = pd.Series(pd.NA, index=out.index, dtype="boolean")
    if mad > 0:
        out.loc[out.model_eligible, "residual_outlier"] = (
            out.loc[out.model_eligible, "funding_residual_per_resident"].sub(center).abs()
            > 3 * 1.4826 * mad)
    centers, converged = _clusters(x, clusters)
    out["typology"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    out.loc[out.model_eligible, "typology"] = (
        (all_x[:, None, :] - centers) ** 2).sum(axis=2).argmin(axis=1)
    out["split"] = np.where(train, "train", np.where(test, "holdout", "excluded"))
    sensitivity = pd.DataFrame(rows)
    cluster_sensitivity = []
    for k in (2, 3, 4):
        if len(np.unique(x, axis=0)) < k:
            continue
        alternatives, stable = _clusters(x, k)
        distances = ((test_x[:, None, :] - alternatives) ** 2).sum(axis=2)
        cluster_sensitivity.append({"k": k, "converged": stable,
                                    "holdout_mean_squared_distance": float(
                                        distances.min(axis=1).mean()),
                                    "holdout_cluster_sizes": np.bincount(
                                        distances.argmin(axis=1), minlength=k).tolist()})
    reference_rank = pd.Series(predictions[1.0]).rank()
    sensitivity["prediction_rank_correlation_to_alpha1"] = [
        float(reference_rank.corr(pd.Series(predictions[a]).rank()))
        if reference_rank.nunique() > 1 and pd.Series(predictions[a]).nunique() > 1 else None
        for a in sensitivity.ridge_alpha]
    report = {
        "publication_status": "exploratory_review_required", "holdout_year": holdout_year,
        "training_rows": int(train.sum()), "holdout_rows": int(test.sum()),
        "excluded_rows": int((~out.model_eligible).sum()),
        "features": FEATURES, "training_feature_mean": mean.tolist(),
        "training_feature_scale": scale.tolist(), "ridge_alpha": 1.0,
        "ridge_coefficients": fitted_beta.tolist(), "cluster_count": clusters,
        "cluster_centers_standardized": centers.tolist(), "clusters_converged": converged,
        "cluster_sensitivity": cluster_sensitivity,
        "baseline_holdout_mae": float(np.abs(test_y - baseline).mean()),
        "baseline_training_median": baseline,
        "outlier_mad": mad, "outlier_center": center,
        "interpretation": "Residuals describe this model, not unmet entitlement or causal gaps",
        "validation_scope": "later years of observed counties; not unseen-county validation",
    }
    return out, sensitivity, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--holdout-year", type=int, required=True)
    parser.add_argument("--clusters", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/modeling"))
    args = parser.parse_args()
    panel = pd.read_csv(args.panel, dtype={"county_fips": "string"})
    result, sensitivity, report = evaluate(
        panel, holdout_year=args.holdout_year, clusters=args.clusters)
    report["input_sha256"] = hashlib.sha256(args.panel.read_bytes()).hexdigest()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output_dir / "county_analysis.csv", index=False)
    sensitivity.to_csv(args.output_dir / "sensitivity.csv", index=False)
    (args.output_dir / "model_report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
