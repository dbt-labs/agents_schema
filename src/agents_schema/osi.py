"""OSI connector: writes agents.osi_* from Open Semantic Interchange YAML files.

Spec: https://open-semantic-interchange.org/
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .destinations import Column, Destination, TableSchema, open_destination
from .root import upsert_provider_root

__all__ = ["run"]

OSI_DATASET = TableSchema(
    "agents.osi_dataset",
    (
        Column("name", "varchar", nullable=False),
        Column("source_table", "varchar", nullable=False),
        Column("primary_key", "array"),
        Column("description", "text"),
        Column("ai_context", "text"),
    ),
    primary_key=("name",),
)
OSI_FIELD = TableSchema(
    "agents.osi_field",
    (
        Column("dataset_name", "varchar", nullable=False),
        Column("field_name", "varchar", nullable=False),
        Column("label", "varchar"),
        Column("description", "text"),
        Column("ai_context", "text"),
        Column("is_time_dimension", "boolean"),
        Column("expression", "text"),
    ),
    primary_key=("dataset_name", "field_name"),
)
OSI_METRIC = TableSchema(
    "agents.osi_metric",
    (
        Column("name", "varchar", nullable=False),
        Column("description", "text"),
        Column("ai_context", "text"),
        Column("expression", "text"),
    ),
    primary_key=("name",),
)
OSI_RELATIONSHIP = TableSchema(
    "agents.osi_relationship",
    (
        Column("name", "varchar", nullable=False),
        Column("from_dataset", "varchar", nullable=False),
        Column("to_dataset", "varchar", nullable=False),
        Column("from_columns", "array", nullable=False),
        Column("to_columns", "array", nullable=False),
    ),
    primary_key=("name",),
)


def run(cfg: dict) -> None:
    osi_dir = Path(cfg["metadata_connection"]["path"])
    models = _load_osi_files(osi_dir)
    with open_destination(cfg) as dest:
        upsert_provider_root(dest, "osi")
        _create_tables(dest)
        _ingest(dest, models)


def _load_osi_files(osi_dir: Path) -> list[dict]:
    files = sorted(osi_dir.glob("*.osi.yaml"))
    if not files:
        raise FileNotFoundError(f"no *.osi.yaml files found in {osi_dir}")
    return [yaml.safe_load(f.read_text()).get("semantic_model", {}) for f in files]


def _create_tables(dest: Destination) -> None:
    dest.replace_table(OSI_DATASET)
    dest.replace_table(OSI_FIELD)
    dest.replace_table(OSI_METRIC)
    dest.replace_table(OSI_RELATIONSHIP)


def _first_expression(expr_obj: dict | None) -> str | None:
    if not expr_obj:
        return None
    dialects = expr_obj.get("dialects", [])
    return dialects[0].get("expression") if dialects else None


def _ingest(dest: Destination, models: list[dict]) -> None:
    datasets, fields, metrics, relationships = [], [], [], []

    for model in models:
        for ds in model.get("datasets", []):
            datasets.append((
                ds["name"],
                ds.get("source", ""),
                list(ds.get("primary_key", [])),
                ds.get("description", ""),
                ds.get("ai_context", ""),
            ))
            for f in ds.get("fields", []):
                dim = f.get("dimension")
                fields.append((
                    ds["name"],
                    f["name"],
                    f.get("label"),
                    f.get("description", ""),
                    f.get("ai_context", ""),
                    bool(dim and dim.get("is_time")),
                    _first_expression(f.get("expression")),
                ))

        for m in model.get("metrics", []):
            metrics.append((
                m["name"],
                m.get("description", ""),
                m.get("ai_context", ""),
                _first_expression(m.get("expression")),
            ))

        for r in model.get("relationships", []):
            relationships.append((
                r["name"],
                r["from"],
                r["to"],
                list(r.get("from_columns", [])),
                list(r.get("to_columns", [])),
            ))

    if datasets:
        dest.insert_rows(OSI_DATASET, datasets)
    if fields:
        dest.insert_rows(OSI_FIELD, fields)
    if metrics:
        dest.insert_rows(OSI_METRIC, metrics)
    if relationships:
        dest.insert_rows(OSI_RELATIONSHIP, relationships)

    print(f"  osi:      {len(datasets)} datasets, {len(fields)} fields, {len(metrics)} metrics, {len(relationships)} relationships")
