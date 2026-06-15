"""Command-line interface for agents-schema."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from . import __version__, dbt, lookml, osi, skills, snowflake_semantic
from .config import ConfigError
from .dbt_profiles import dbt_adapter_package_from_profiles_file
from .destinations import warehouse_type_from_env


def _config(source_type: str, path: Path) -> dict[str, Any]:
    return {
        "warehouse": {"type": warehouse_type_from_env()},
        "metadata_connection": {
            "type": source_type,
            "path": str(path),
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agents-schema",
        description="Populate the AGENTS schema in a supported warehouse from metadata sources.",
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

    osi_parser = sub.add_parser(
        "osi",
        help="ingest Open Semantic Interchange YAML into AGENTS.OSI_*",
    )
    osi_parser.add_argument(
        "--osi-dir",
        required=True,
        type=Path,
        help="path to a directory containing *.osi.yaml files",
    )

    skills_parser = sub.add_parser(
        "skills",
        help="ingest markdown skills into AGENTS.ROOT",
    )
    skills_parser.add_argument(
        "--skills-dir",
        required=True,
        type=Path,
        help="path to a directory containing markdown skill files",
    )
    skills_parser.add_argument(
        "--provider",
        default="user",
        help="publisher name to use for AGENTS.ROOT skill rows",
    )

    snowflake_semantic_parser = sub.add_parser(
        "snowflake-semantic",
        help="publish Snowflake semantic view pointers into AGENTS.ROOT",
    )
    snowflake_semantic_parser.add_argument(
        "--semantic-view",
        action="append",
        required=True,
        dest="semantic_views",
        help="fully qualified Snowflake semantic view name; repeat for multiple views",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.source_type == "dbt":
            dbt.run(_config("dbt", args.project_dir))
        elif args.source_type == "looker":
            lookml.run(_config("looker", args.lookml_dir))
        elif args.source_type == "osi":
            osi.run(_config("osi", args.osi_dir))
        elif args.source_type == "skills":
            cfg = _config("skills", args.skills_dir)
            cfg["metadata_connection"]["provider"] = args.provider
            skills.run(cfg)
        elif args.source_type == "snowflake-semantic":
            cfg = {
                "warehouse": {"type": warehouse_type_from_env()},
                "metadata_connection": {
                    "type": "snowflake-semantic",
                    "semantic_views": args.semantic_views,
                },
            }
            snowflake_semantic.run(cfg)
        else:
            raise ConfigError(f"unsupported source type: {args.source_type}")
    except (ConfigError, FileNotFoundError) as e:
        print(f"agents-schema: error: {e}", file=sys.stderr)
        return 1
    return 0


def dbt_adapter_package_main(argv: list[str] | None = None) -> int:
    actual_argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(prog="agents-schema-dbt-adapter-package")
    parser.add_argument("--profiles-yml", required=True, type=Path)
    parser.add_argument("--profile-name", required=True)
    parser.add_argument("--target", default=None)
    args = parser.parse_args(actual_argv)
    try:
        print(dbt_adapter_package_from_profiles_file(args.profiles_yml, args.profile_name, args.target))
    except ConfigError as e:
        print(f"agents-schema-dbt-adapter-package: error: {e}", file=sys.stderr)
        return 1
    return 0
