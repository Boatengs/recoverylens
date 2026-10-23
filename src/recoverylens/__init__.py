"""RecoveryLens: reproducible disaster recovery equity analysis."""

from .coverage import CoverageThresholds, assess_county_coverage
from .metrics import EquityWeights, calculate_equity_score
from .noaa import (
    StormEventsDownloadResult,
    StormEventsFile,
    VerifiedStormEventsFile,
    catalog_storm_events_files,
    download_storm_events_files,
    select_storm_events_files,
    verified_storm_events_files,
)
from .obligations import ObligationMetricsResult, analyze_obligation_metrics
from .quality import PAQualityReport, build_pa_quality_report
from .reconciliation import ReconciliationTolerance, reconcile_pa_projects
from .storm_damage import (
    DamageAmount,
    StormDamageResult,
    analyze_storm_event_damage,
    parse_damage_amount,
    read_storm_event_details,
)

__all__ = [
    "EquityWeights",
    "CoverageThresholds",
    "DamageAmount",
    "ObligationMetricsResult",
    "PAQualityReport",
    "ReconciliationTolerance",
    "StormEventsDownloadResult",
    "StormEventsFile",
    "StormDamageResult",
    "VerifiedStormEventsFile",
    "analyze_storm_event_damage",
    "assess_county_coverage",
    "analyze_obligation_metrics",
    "build_pa_quality_report",
    "calculate_equity_score",
    "catalog_storm_events_files",
    "download_storm_events_files",
    "parse_damage_amount",
    "read_storm_event_details",
    "reconcile_pa_projects",
    "select_storm_events_files",
    "verified_storm_events_files",
]
__version__ = "0.1.0"
