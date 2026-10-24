"""Command-line interface for reproducible RecoveryLens data pulls."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from .coverage import CoverageThresholds, assess_county_coverage
from .fema import (
    Query,
    aggregate_county_declarations,
    aggregate_county_pa_projects,
    declaration_filter,
    declaration_matching_filter,
    iter_records,
    pa_project_filter,
    prepare_county_declarations,
    prepare_pa_projects,
)
from .noaa import (
    SUPPORTED_STORM_DATASETS,
    download_storm_events_files,
    fetch_storm_events_catalog,
    select_storm_events_files,
    verified_storm_events_files,
)
from .obligations import analyze_obligation_metrics
from .quality import build_pa_quality_report, write_quality_report
from .reconciliation import ReconciliationTolerance, reconcile_pa_projects
from .storm_damage import analyze_storm_event_damage, read_storm_event_details
from .storm_impacts import analyze_storm_event_impacts, read_storm_event_fatalities
from .storm_matching import (
    FEMA_MATCH_COLUMNS,
    assess_event_declaration_candidates,
    prepare_storm_events,
    read_storm_event_matching_details,
)

PA_PROJECT_FIELDS = (
    "disasterNumber",
    "stateAbbreviation",
    "county",
    "stateNumberCode",
    "countyCode",
    "damageCategoryCode",
    "projectStatus",
    "gmProjectId",
    "projectAmount",
    "federalShareObligated",
    "totalObligated",
    "declarationDate",
    "firstObligationDate",
    "lastObligationDate",
)


def declaration_command(args: argparse.Namespace) -> int:
    query = Query(
        dataset="declarations",
        filter_expression=declaration_filter(state=args.state, start_year=args.start_year),
        select=(
            "disasterNumber",
            "state",
            "designatedArea",
            "declarationDate",
            "incidentType",
            "fipsStateCode",
            "fipsCountyCode",
        ),
        order_by="disasterNumber asc",
        max_records=args.max_records,
    )
    records = list(iter_records(query))
    counties = aggregate_county_declarations(prepare_county_declarations(records))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    counties.to_csv(output, index=False)
    print(f"Wrote {len(counties):,} county records to {output}")
    return 0


def noaa_download_command(args: argparse.Namespace) -> int:
    catalog = fetch_storm_events_catalog()
    selected = select_storm_events_files(
        catalog,
        dataset=args.dataset,
        start_year=args.start_year,
        end_year=args.end_year,
        schema_version=args.schema_version,
    )
    retrieved_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    result = download_storm_events_files(
        selected,
        args.output_dir,
        retrieved_at=retrieved_at,
    )
    print(
        f"NOAA Storm Events: {result.downloaded_count:,} downloaded, "
        f"{result.reused_count:,} verified and reused; manifest at {result.manifest_path}"
    )
    return 0


def noaa_damage_command(args: argparse.Namespace) -> int:
    verified = verified_storm_events_files(
        args.input_dir,
        dataset="details",
        start_year=args.start_year,
        end_year=args.end_year,
        schema_version=args.schema_version,
    )
    result = analyze_storm_event_damage(read_storm_event_details(verified))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result.events.to_csv(output_dir / "event_damage.csv", index=False)
    result.by_year.to_csv(output_dir / "damage_by_year.csv", index=False)
    (output_dir / "summary.json").write_text(
        json.dumps(result.summary, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"NOAA damage status: {result.summary['publication_status']}; "
        f"parsed {result.summary['event_count']:,} events into {output_dir}"
    )
    return 0


def noaa_impacts_command(args: argparse.Namespace) -> int:
    details = verified_storm_events_files(
        args.input_dir,
        dataset="details",
        start_year=args.start_year,
        end_year=args.end_year,
        schema_version=args.schema_version,
    )
    fatalities = verified_storm_events_files(
        args.input_dir,
        dataset="fatalities",
        start_year=args.start_year,
        end_year=args.end_year,
        schema_version=args.schema_version,
    )
    result = analyze_storm_event_impacts(
        read_storm_event_details(details),
        read_storm_event_fatalities(fatalities),
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result.events.to_csv(output_dir / "event_impacts.csv", index=False)
    result.by_year.to_csv(output_dir / "impacts_by_year.csv", index=False)
    result.unmatched_fatalities.to_csv(
        output_dir / "unmatched_fatality_records.csv",
        index=False,
    )
    (output_dir / "summary.json").write_text(
        json.dumps(result.summary, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"NOAA impact status: {result.summary['publication_status']}; "
        f"aggregated {result.summary['included_event_count']:,} events into {output_dir}"
    )
    return 0


def noaa_fema_match_command(args: argparse.Namespace) -> int:
    details = verified_storm_events_files(
        args.input_dir,
        dataset="details",
        start_year=args.start_year,
        end_year=args.end_year,
        schema_version=args.schema_version,
    )
    raw_events = read_storm_event_matching_details(details)
    prepared_events = prepare_storm_events(raw_events)
    eligible = prepared_events.loc[prepared_events["match_status"].eq("eligible")]
    event_start = None if eligible.empty else eligible["event_begin_date"].min().date()
    event_end = None if eligible.empty else eligible["event_end_date"].max().date()
    query = Query(
        dataset="declarations",
        filter_expression=declaration_matching_filter(
            start_year=args.start_year,
            end_year=args.end_year,
            date_buffer_days=args.date_buffer_days,
            event_start_date=event_start,
            event_end_date=event_end,
        ),
        select=FEMA_MATCH_COLUMNS,
        order_by="disasterNumber asc",
        max_records=args.max_declaration_records,
    )
    records = list(iter_records(query))
    record_limit_reached = (
        args.max_declaration_records is not None
        and len(records) >= args.max_declaration_records
    )
    result = assess_event_declaration_candidates(
        raw_events,
        records,
        date_buffer_days=args.date_buffer_days,
        declaration_record_limit_reached=record_limit_reached,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result.events.to_csv(output_dir / "event_assessments.csv", index=False)
    result.declarations.to_csv(output_dir / "declaration_windows.csv", index=False)
    result.candidates.to_csv(output_dir / "candidate_links.csv", index=False)
    result.review_queue.to_csv(output_dir / "review_queue.csv", index=False)
    summary = {
        **result.summary,
        "requested_end_year": args.end_year,
        "requested_start_year": args.start_year,
        "fema_filter": query.filter_expression,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"FEMA–NOAA candidate assessment: {summary['publication_status']}; "
        f"{summary['candidate_event_count']:,}/{summary['eligible_event_count']:,} "
        f"eligible events have candidates in {output_dir}"
    )
    return 0


def pa_projects_command(args: argparse.Namespace) -> int:
    query = Query(
        dataset="pa_projects",
        filter_expression=pa_project_filter(
            state=args.state,
            start_year=args.start_year,
            disaster_number=args.disaster_number,
        ),
        select=PA_PROJECT_FIELDS,
        order_by="disasterNumber asc",
        max_records=args.max_records,
    )
    records = list(iter_records(query))
    counties = aggregate_county_pa_projects(prepare_pa_projects(records))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    counties.to_csv(output, index=False)
    print(f"Wrote {len(counties):,} county funding records to {output}")
    return 0


def pa_reconciliation_command(args: argparse.Namespace) -> int:
    query = Query(
        dataset="pa_projects",
        filter_expression=pa_project_filter(
            state=args.state,
            start_year=args.start_year,
            disaster_number=args.disaster_number,
        ),
        select=PA_PROJECT_FIELDS,
        order_by="disasterNumber asc",
        max_records=args.max_records,
    )
    records = list(iter_records(query))
    prepared = prepare_pa_projects(records)
    result = reconcile_pa_projects(
        prepared,
        tolerance=ReconciliationTolerance(
            absolute_dollars=args.absolute_tolerance,
            relative=args.relative_tolerance,
        ),
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result.curated_projects.to_csv(output_dir / "curated_projects.csv", index=False)
    result.duplicate_projects.to_csv(output_dir / "duplicate_projects.csv", index=False)
    result.disaster_totals.to_csv(output_dir / "disaster_totals.csv", index=False)
    result.state_totals.to_csv(output_dir / "state_totals.csv", index=False)
    (output_dir / "summary.json").write_text(
        json.dumps(result.summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"Reconciled {result.summary['source_record_count']:,} source records; "
        f"wrote outputs to {output_dir}"
    )
    return 0


def pa_coverage_command(args: argparse.Namespace) -> int:
    query = Query(
        dataset="pa_projects",
        filter_expression=pa_project_filter(
            state=args.state,
            start_year=args.start_year,
            disaster_number=args.disaster_number,
        ),
        select=PA_PROJECT_FIELDS,
        order_by="disasterNumber asc",
        max_records=args.max_records,
    )
    records = list(iter_records(query))
    prepared = prepare_pa_projects(records)
    reconciliation = reconcile_pa_projects(prepared)
    result = assess_county_coverage(
        reconciliation.curated_projects,
        thresholds=CoverageThresholds(
            minimum_record_coverage=args.minimum_record_coverage,
            minimum_obligation_coverage=args.minimum_obligation_coverage,
        ),
    )
    summary = {
        **result.summary,
        "source_record_count": reconciliation.summary["source_record_count"],
        "curated_record_count": reconciliation.summary["curated_record_count"],
        "duplicate_key_count": reconciliation.summary["duplicate_key_count"],
        "conflicting_key_count": reconciliation.summary["conflicting_key_count"],
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result.coverage_by_status.to_csv(output_dir / "coverage_by_status.csv", index=False)
    result.unmatched_projects.to_csv(output_dir / "unmatched_projects.csv", index=False)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"County attribution status: {summary['publication_status']}; "
        f"{summary['attributed_record_count']:,}/{summary['input_record_count']:,} "
        f"curated records attributed"
    )
    return 0


def pa_quality_report_command(args: argparse.Namespace) -> int:
    filters = {
        "disaster_number": args.disaster_number,
        "start_year": args.start_year,
        "state": args.state.upper() if args.state else None,
    }
    query = Query(
        dataset="pa_projects",
        filter_expression=pa_project_filter(
            state=args.state,
            start_year=args.start_year,
            disaster_number=args.disaster_number,
        ),
        select=PA_PROJECT_FIELDS,
        order_by="disasterNumber asc",
        max_records=args.max_records,
    )
    records = list(iter_records(query))
    retrieved_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    prepared = prepare_pa_projects(records)
    reconciliation = reconcile_pa_projects(
        prepared,
        tolerance=ReconciliationTolerance(
            absolute_dollars=args.absolute_tolerance,
            relative=args.relative_tolerance,
        ),
    )
    coverage = assess_county_coverage(
        reconciliation.curated_projects,
        thresholds=CoverageThresholds(
            minimum_record_coverage=args.minimum_record_coverage,
            minimum_obligation_coverage=args.minimum_obligation_coverage,
        ),
    )
    obligations = analyze_obligation_metrics(reconciliation.curated_projects)
    report = build_pa_quality_report(
        records,
        reconciliation,
        coverage,
        query=query,
        retrieved_at=retrieved_at,
        filters=filters,
        obligations=obligations,
    )
    output_dir = Path(args.output_dir)
    write_quality_report(report, output_dir)
    print(
        f"Quality report status: {report.data['validation']['status']}; "
        f"wrote JSON and Markdown to {output_dir}"
    )
    return 0


def pa_obligations_command(args: argparse.Namespace) -> int:
    query = Query(
        dataset="pa_projects",
        filter_expression=pa_project_filter(
            state=args.state,
            start_year=args.start_year,
            disaster_number=args.disaster_number,
        ),
        select=PA_PROJECT_FIELDS,
        order_by="disasterNumber asc",
        max_records=args.max_records,
    )
    records = list(iter_records(query))
    prepared = prepare_pa_projects(records)
    reconciliation = reconcile_pa_projects(prepared)
    result = analyze_obligation_metrics(reconciliation.curated_projects)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result.projects.to_csv(output_dir / "project_obligation_timing.csv", index=False)
    result.category_summary.to_csv(output_dir / "category_summary.csv", index=False)
    (output_dir / "summary.json").write_text(
        json.dumps(result.summary, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"Obligation metrics status: {result.summary['publication_status']}; "
        f"analyzed {result.summary['project_count']:,} curated projects"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="recoverylens")
    subparsers = parser.add_subparsers(dest="command", required=True)
    declarations = subparsers.add_parser(
        "declarations", help="Fetch and aggregate FEMA major-disaster declarations"
    )
    declarations.add_argument("--state", help="Optional two-letter state abbreviation")
    declarations.add_argument("--start-year", type=int, default=2000)
    declarations.add_argument("--max-records", type=int)
    declarations.add_argument(
        "--output", default="data/processed/county_declarations.csv"
    )
    declarations.set_defaults(handler=declaration_command)

    noaa_download = subparsers.add_parser(
        "noaa-download",
        help="Download versioned NOAA Storm Events annual files",
    )
    noaa_download.add_argument(
        "--dataset",
        choices=SUPPORTED_STORM_DATASETS,
        default="details",
    )
    noaa_download.add_argument("--start-year", type=int, required=True)
    noaa_download.add_argument("--end-year", type=int, required=True)
    noaa_download.add_argument(
        "--schema-version",
        help="Optional NOAA CSV schema version such as 1.0",
    )
    noaa_download.add_argument(
        "--output-dir",
        default="data/raw/noaa/storm-events",
    )
    noaa_download.set_defaults(handler=noaa_download_command)

    noaa_damage = subparsers.add_parser(
        "noaa-damage",
        help="Parse verified NOAA property and crop damage estimates",
    )
    noaa_damage.add_argument("--start-year", type=int, required=True)
    noaa_damage.add_argument("--end-year", type=int, required=True)
    noaa_damage.add_argument(
        "--schema-version",
        help="Optional NOAA CSV schema version such as 1.0",
    )
    noaa_damage.add_argument(
        "--input-dir",
        default="data/raw/noaa/storm-events",
    )
    noaa_damage.add_argument(
        "--output-dir",
        default="data/processed/noaa/damage",
    )
    noaa_damage.set_defaults(handler=noaa_damage_command)

    noaa_impacts = subparsers.add_parser(
        "noaa-impacts",
        help="Aggregate NOAA injuries and reconcile fatality counts",
    )
    noaa_impacts.add_argument("--start-year", type=int, required=True)
    noaa_impacts.add_argument("--end-year", type=int, required=True)
    noaa_impacts.add_argument(
        "--schema-version",
        help="Optional NOAA CSV schema version such as 1.0",
    )
    noaa_impacts.add_argument(
        "--input-dir",
        default="data/raw/noaa/storm-events",
    )
    noaa_impacts.add_argument(
        "--output-dir",
        default="data/processed/noaa/impacts",
    )
    noaa_impacts.set_defaults(handler=noaa_impacts_command)

    noaa_fema_match = subparsers.add_parser(
        "noaa-fema-match",
        help="Assess county/date candidate links between NOAA events and FEMA declarations",
    )
    noaa_fema_match.add_argument("--start-year", type=int, required=True)
    noaa_fema_match.add_argument("--end-year", type=int, required=True)
    noaa_fema_match.add_argument(
        "--schema-version",
        help="Optional NOAA CSV schema version such as 1.0",
    )
    noaa_fema_match.add_argument(
        "--date-buffer-days",
        type=int,
        default=0,
        help="Maximum gap in days allowed between event and incident windows (default: 0)",
    )
    noaa_fema_match.add_argument(
        "--max-declaration-records",
        type=int,
        default=50_000,
        help="Maximum FEMA declaration-area rows to retrieve (default: 50,000)",
    )
    noaa_fema_match.add_argument(
        "--input-dir",
        default="data/raw/noaa/storm-events",
    )
    noaa_fema_match.add_argument(
        "--output-dir",
        default="data/processed/noaa/fema_match",
    )
    noaa_fema_match.set_defaults(handler=noaa_fema_match_command)

    pa_projects = subparsers.add_parser(
        "pa-projects", help="Fetch and aggregate FEMA Public Assistance funded projects"
    )
    pa_projects.add_argument("--state", help="Optional two-letter state abbreviation")
    pa_projects.add_argument("--start-year", type=int, default=2000)
    pa_projects.add_argument("--disaster-number", type=int)
    pa_projects.add_argument(
        "--max-records",
        type=int,
        default=10_000,
        help="Maximum source records to retrieve (default: 10,000)",
    )
    pa_projects.add_argument(
        "--output", default="data/processed/county_pa_projects.csv"
    )
    pa_projects.set_defaults(handler=pa_projects_command)

    pa_reconciliation = subparsers.add_parser(
        "pa-reconcile",
        help="Reconcile source and curated Public Assistance funding totals",
    )
    pa_reconciliation.add_argument("--state", help="Optional two-letter state abbreviation")
    pa_reconciliation.add_argument("--start-year", type=int, default=2000)
    pa_reconciliation.add_argument("--disaster-number", type=int)
    pa_reconciliation.add_argument("--max-records", type=int, default=10_000)
    pa_reconciliation.add_argument("--absolute-tolerance", type=float, default=0.01)
    pa_reconciliation.add_argument("--relative-tolerance", type=float, default=1e-9)
    pa_reconciliation.add_argument(
        "--output-dir", default="data/processed/pa_reconciliation"
    )
    pa_reconciliation.set_defaults(handler=pa_reconciliation_command)

    pa_coverage = subparsers.add_parser(
        "pa-coverage",
        help="Measure and report county-attribution coverage",
    )
    pa_coverage.add_argument("--state", help="Optional two-letter state abbreviation")
    pa_coverage.add_argument("--start-year", type=int, default=2000)
    pa_coverage.add_argument("--disaster-number", type=int)
    pa_coverage.add_argument("--max-records", type=int, default=10_000)
    pa_coverage.add_argument("--minimum-record-coverage", type=float, default=0.95)
    pa_coverage.add_argument("--minimum-obligation-coverage", type=float, default=0.95)
    pa_coverage.add_argument("--output-dir", default="data/processed/pa_coverage")
    pa_coverage.set_defaults(handler=pa_coverage_command)

    pa_quality = subparsers.add_parser(
        "pa-quality-report",
        help="Generate machine- and human-readable Public Assistance quality reports",
    )
    pa_quality.add_argument("--state", help="Optional two-letter state abbreviation")
    pa_quality.add_argument("--start-year", type=int, default=2000)
    pa_quality.add_argument("--disaster-number", type=int)
    pa_quality.add_argument("--max-records", type=int, default=10_000)
    pa_quality.add_argument("--absolute-tolerance", type=float, default=0.01)
    pa_quality.add_argument("--relative-tolerance", type=float, default=1e-9)
    pa_quality.add_argument("--minimum-record-coverage", type=float, default=0.95)
    pa_quality.add_argument("--minimum-obligation-coverage", type=float, default=0.95)
    pa_quality.add_argument("--output-dir", default="data/processed/pa_quality")
    pa_quality.set_defaults(handler=pa_quality_report_command)

    pa_obligations = subparsers.add_parser(
        "pa-obligations",
        help="Analyze Public Assistance work categories and obligation timing",
    )
    pa_obligations.add_argument("--state", help="Optional two-letter state abbreviation")
    pa_obligations.add_argument("--start-year", type=int, default=2000)
    pa_obligations.add_argument("--disaster-number", type=int)
    pa_obligations.add_argument("--max-records", type=int, default=10_000)
    pa_obligations.add_argument(
        "--output-dir", default="data/processed/pa_obligations"
    )
    pa_obligations.set_defaults(handler=pa_obligations_command)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
