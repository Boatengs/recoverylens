"""Command-line interface for reproducible RecoveryLens data pulls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .fema import (
    Query,
    aggregate_county_declarations,
    aggregate_county_pa_projects,
    declaration_filter,
    iter_records,
    pa_project_filter,
    prepare_county_declarations,
    prepare_pa_projects,
)
from .reconciliation import ReconciliationTolerance, reconcile_pa_projects

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
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
