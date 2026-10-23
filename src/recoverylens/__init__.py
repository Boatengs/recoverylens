"""RecoveryLens: reproducible disaster recovery equity analysis."""

from .coverage import CoverageThresholds, assess_county_coverage
from .metrics import EquityWeights, calculate_equity_score
from .quality import PAQualityReport, build_pa_quality_report
from .reconciliation import ReconciliationTolerance, reconcile_pa_projects

__all__ = [
    "EquityWeights",
    "CoverageThresholds",
    "PAQualityReport",
    "ReconciliationTolerance",
    "assess_county_coverage",
    "build_pa_quality_report",
    "calculate_equity_score",
    "reconcile_pa_projects",
]
__version__ = "0.1.0"
