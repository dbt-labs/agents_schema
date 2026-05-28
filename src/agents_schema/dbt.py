"""dbt manifest connector: writes agents.dbt_* from a compiled dbt manifest."""
from __future__ import annotations

import json
from pathlib import Path

from .destinations import Column, Destination, TableSchema, open_destination
from .root import upsert_provider_root

__all__ = ["run"]

DBT_MODEL = TableSchema(
    "agents.dbt_model",
    (
        Column("unique_id", "varchar", nullable=False),
        Column("name", "varchar", nullable=False),
        Column("schema_name", "varchar"),
        Column("materialization", "varchar"),
        Column("description", "text"),
        Column("file_path", "varchar"),
        Column("tags", "array"),
    ),
    primary_key=("unique_id",),
)
DBT_COLUMN = TableSchema(
    "agents.dbt_column",
    (
        Column("model_id", "varchar", nullable=False),
        Column("column_name", "varchar", nullable=False),
        Column("data_type", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("model_id", "column_name"),
)
DBT_DEPENDENCY = TableSchema(
    "agents.dbt_dependency",
    (
        Column("upstream_id", "varchar", nullable=False),
        Column("downstream_id", "varchar", nullable=False),
        Column("upstream_type", "varchar"),
        Column("downstream_type", "varchar"),
    ),
    primary_key=("upstream_id", "downstream_id"),
)


def run(cfg: dict) -> None:
    manifest_path = Path(cfg["metadata_connection"]["path"]) / "target" / "manifest.json"
    manifest = _load_manifest(manifest_path)
    with open_destination(cfg) as dest:
        upsert_provider_root(dest, "dbt")
        _create_tables(dest)
        _ingest(dest, manifest)


def _load_manifest(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"dbt manifest not found at {path}\n"
            "  run `dbt parse`, `dbt compile`, `dbt build`, or `dbt run` first"
        )
    return json.loads(path.read_text())


def _create_tables(dest: Destination) -> None:
    dest.replace_table(DBT_MODEL)
    dest.replace_table(DBT_COLUMN)
    dest.replace_table(DBT_DEPENDENCY)


def _ingest(dest: Destination, manifest: dict) -> None:
    models, columns, dependencies = [], [], []

    for uid, node in manifest.get("nodes", {}).items():
        if node.get("resource_type") != "model":
            continue

        models.append((
            uid,
            node["name"],
            node.get("schema"),
            node.get("config", {}).get("materialized"),
            node.get("description") or "",
            node.get("original_file_path"),
            list(node.get("tags", [])),
        ))

        for col_name, col_info in node.get("columns", {}).items():
            columns.append((
                uid,
                col_name,
                col_info.get("data_type") or "",
                col_info.get("description") or "",
            ))

        for dep_uid in node.get("depends_on", {}).get("nodes", []):
            dep_type = dep_uid.split(".")[0] if "." in dep_uid else "unknown"
            dependencies.append((dep_uid, uid, dep_type, "model"))

    if models:
        dest.insert_rows(DBT_MODEL, models)
    if columns:
        dest.insert_rows(DBT_COLUMN, columns)
    if dependencies:
        dest.insert_rows(DBT_DEPENDENCY, dependencies)

    print(f"  dbt:      {len(models)} models, {len(columns)} columns, {len(dependencies)} deps")
