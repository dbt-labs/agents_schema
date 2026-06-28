"""OSI connector: writes agents.osi_* from Open Semantic Interchange YAML files.

Spec: https://open-semantic-interchange.org/
Vendored schema: src/agents_schema/osi-schema.json — copied verbatim from
open-semantic-interchange/OSI core-spec/osi-schema.json (OSI v0.2.0.dev0).
Bump it deliberately when OSI releases a new schema version.

The OSI document shape (see the vendored schema):
- top level: ``version`` + ``semantic_model`` (an ARRAY of models)
- each model: ``name``, ``description``, ``ai_context``, ``datasets``,
  ``metrics``, ``relationships``, ``custom_extensions``
- ``ai_context`` is a string OR an object (``synonyms``/``instructions``/…)
- ``expression`` carries ``dialects: [{dialect, expression}, …]`` (>= 1)
- ``custom_extensions`` is an array of ``{vendor_name, data}``
"""
from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from .destinations import Column, Destination, TableSchema, open_destination
from .root import upsert_provider_root

__all__ = ["run"]

# VARIANT columns reuse the destinations' "array" kind (JSON-encoded on insert).
OSI_MODEL = TableSchema(
    "agents.osi_model",
    (
        Column("name", "varchar", nullable=False),
        Column("version", "varchar"),
        Column("description", "text"),
        Column("synonyms", "array"),
        Column("ai_context", "array"),
        Column("custom_extensions", "array"),
    ),
    primary_key=("name",),
)
OSI_DATASET = TableSchema(
    "agents.osi_dataset",
    (
        Column("model_name", "varchar", nullable=False),
        Column("name", "varchar", nullable=False),
        Column("source", "varchar", nullable=False),
        Column("primary_key", "array"),
        Column("unique_keys", "array"),
        Column("description", "text"),
        Column("synonyms", "array"),
        Column("ai_context", "array"),
        Column("custom_extensions", "array"),
    ),
    primary_key=("model_name", "name"),
)
OSI_FIELD = TableSchema(
    "agents.osi_field",
    (
        Column("dataset_name", "varchar", nullable=False),
        Column("name", "varchar", nullable=False),
        Column("label", "varchar"),
        Column("description", "text"),
        Column("is_time_dimension", "boolean"),
        Column("expressions", "array"),
        Column("synonyms", "array"),
        Column("ai_context", "array"),
        Column("custom_extensions", "array"),
    ),
    primary_key=("dataset_name", "name"),
)
OSI_METRIC = TableSchema(
    "agents.osi_metric",
    (
        Column("model_name", "varchar", nullable=False),
        Column("name", "varchar", nullable=False),
        Column("description", "text"),
        Column("expressions", "array"),
        Column("synonyms", "array"),
        Column("ai_context", "array"),
        Column("custom_extensions", "array"),
    ),
    primary_key=("model_name", "name"),
)
OSI_RELATIONSHIP = TableSchema(
    "agents.osi_relationship",
    (
        Column("model_name", "varchar", nullable=False),
        Column("name", "varchar", nullable=False),
        Column("from_dataset", "varchar", nullable=False),
        Column("to_dataset", "varchar", nullable=False),
        Column("from_columns", "array", nullable=False),
        Column("to_columns", "array", nullable=False),
        Column("synonyms", "array"),
        Column("ai_context", "array"),
        Column("custom_extensions", "array"),
    ),
    primary_key=("model_name", "name"),
)

_TABLES = (OSI_MODEL, OSI_DATASET, OSI_FIELD, OSI_METRIC, OSI_RELATIONSHIP)
_SCHEMA = json.loads((resources.files("agents_schema") / "osi-schema.json").read_text())


def run(cfg: dict) -> None:
    osi_dir = Path(cfg["metadata_connection"]["path"])
    docs = _load_osi_files(osi_dir)
    with open_destination(cfg) as dest:
        upsert_provider_root(dest, "osi")
        _create_tables(dest)
        _ingest(dest, docs)


def _load_osi_files(osi_dir: Path) -> list[dict]:
    files = sorted(osi_dir.glob("*.osi.yaml"))
    if not files:
        raise FileNotFoundError(f"no *.osi.yaml files found in {osi_dir}")
    docs = []
    for f in files:
        doc = yaml.safe_load(f.read_text())
        _validate(doc, f)
        docs.append(doc)
    return docs


def _validate(doc: Any, path: Path) -> None:
    try:
        jsonschema.validate(doc, _SCHEMA)
    except jsonschema.ValidationError as e:
        loc = "/" + "/".join(str(p) for p in e.absolute_path)
        raise ValueError(f"{path}: OSI schema validation failed at {loc}: {e.message}") from e


def _create_tables(dest: Destination) -> None:
    for table in _TABLES:
        dest.replace_table(table)


def _ai_context(ctx: Any) -> tuple[list[str], Any]:
    """Return (synonyms, raw_ai_context). ai_context is a string or an object."""
    if ctx is None:
        return [], None
    if isinstance(ctx, str):
        return [], ctx
    return list(ctx.get("synonyms", [])), ctx


def _dialects(expr: Any) -> list[dict]:
    return list((expr or {}).get("dialects", []))


def _ingest(dest: Destination, docs: list[dict]) -> None:
    models, datasets, fields, metrics, relationships = [], [], [], [], []

    for doc in docs:
        version = doc.get("version")
        for model in doc.get("semantic_model", []):
            mname = model["name"]
            syn, ctx = _ai_context(model.get("ai_context"))
            models.append((
                mname,
                version,
                model.get("description", ""),
                syn,
                ctx,
                model.get("custom_extensions"),
            ))

            for ds in model.get("datasets", []):
                dsyn, dctx = _ai_context(ds.get("ai_context"))
                datasets.append((
                    mname,
                    ds["name"],
                    ds["source"],
                    list(ds.get("primary_key", [])),
                    list(ds.get("unique_keys", [])),
                    ds.get("description", ""),
                    dsyn,
                    dctx,
                    ds.get("custom_extensions"),
                ))
                for fld in ds.get("fields", []):
                    fsyn, fctx = _ai_context(fld.get("ai_context"))
                    dim = fld.get("dimension") or {}
                    fields.append((
                        ds["name"],
                        fld["name"],
                        fld.get("label"),
                        fld.get("description", ""),
                        bool(dim.get("is_time")),
                        _dialects(fld.get("expression")),
                        fsyn,
                        fctx,
                        fld.get("custom_extensions"),
                    ))

            for m in model.get("metrics", []):
                msyn, mctx = _ai_context(m.get("ai_context"))
                metrics.append((
                    mname,
                    m["name"],
                    m.get("description", ""),
                    _dialects(m.get("expression")),
                    msyn,
                    mctx,
                    m.get("custom_extensions"),
                ))

            for r in model.get("relationships", []):
                rsyn, rctx = _ai_context(r.get("ai_context"))
                relationships.append((
                    mname,
                    r["name"],
                    r["from"],
                    r["to"],
                    list(r["from_columns"]),
                    list(r["to_columns"]),
                    rsyn,
                    rctx,
                    r.get("custom_extensions"),
                ))

    for table, rows in zip(_TABLES, (models, datasets, fields, metrics, relationships)):
        if rows:
            dest.insert_rows(table, rows)

    print(
        f"  osi:      {len(models)} models, {len(datasets)} datasets, {len(fields)} fields, "
        f"{len(metrics)} metrics, {len(relationships)} relationships"
    )
