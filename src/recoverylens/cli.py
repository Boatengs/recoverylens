"""Command-line interface for reproducible RecoveryLens data pulls."""

from __future__ import annotations

import argparse
from pathlib import Path

from .fema import (
    Query,
    aggregate_county_declarations,
    declaration_filter,
    iter_records,
    prepare_county_declarations,
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
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
