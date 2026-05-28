"""Command-line interface for agents-schema."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from . import __version__, dbt, lookml
from .config import ConfigError


def _config(source_type: str, path: Path) -> dict[str, Any]:
    return {
        "warehouse": {"type": "snowflake"},
        "metadata_connection": {
            "type": source_type,
            "path": str(path),
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agents-schema",
        description="Populate the AGENTS schema in Snowflake from metadata sources.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="source_type", metavar="SOURCE_TYPE", required=True)

    dbt_parser = sub.add_parser(
        "dbt",
        help="ingest dbt manifest into AGENTS.DBT_*",
    )
    dbt_parser.add_argument(
        "--project-dir",
        required=True,
        type=Path,
        help="path to the dbt project containing target/manifest.json",
    )

    looker_parser = sub.add_parser(
        "looker",
        help="ingest LookML files into AGENTS.LOOKML_*",
    )
    looker_parser.add_argument(
        "--lookml-dir",
        required=True,
        type=Path,
        help="path to a Looker project or directory containing *.lkml files",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.source_type == "dbt":
            dbt.run(_config("dbt", args.project_dir))
        elif args.source_type == "looker":
            lookml.run(_config("looker", args.lookml_dir))
        else:
            raise ConfigError(f"unsupported source type: {args.source_type}")
    except (ConfigError, FileNotFoundError) as e:
        print(f"agents-schema: error: {e}", file=sys.stderr)
        return 1
    return 0
