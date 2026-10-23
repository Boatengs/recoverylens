"""RecoveryLens: reproducible disaster recovery equity analysis."""

from .coverage import CoverageThresholds, assess_county_coverage
from .metrics import EquityWeights, calculate_equity_score
from .noaa import (
    StormEventsDownloadResult,
    StormEventsFile,
    catalog_storm_events_files,
    download_storm_events_files,
    select_storm_events_files,
)
from .obligations import ObligationMetricsResult, analyze_obligation_metrics
from .quality import PAQualityReport, build_pa_quality_report
from .reconciliation import ReconciliationTolerance, reconcile_pa_projects

__all__ = [
    "EquityWeights",
    "CoverageThresholds",
    "ObligationMetricsResult",
    "PAQualityReport",
    "ReconciliationTolerance",
    "StormEventsDownloadResult",
    "StormEventsFile",
    "assess_county_coverage",
    "analyze_obligation_metrics",
    "build_pa_quality_report",
    "calculate_equity_score",
    "catalog_storm_events_files",
    "download_storm_events_files",
    "reconcile_pa_projects",
    "select_storm_events_files",
]
__version__ = "0.1.0"
