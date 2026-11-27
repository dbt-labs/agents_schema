"""OSI connector: writes AGENTS.OSI_* from Open Semantic Interchange YAML files.

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

from .config import warehouse_type
from .destinations import Column, Destination, TableSchema, open_destination
from .root import upsert_provider_root
from .skills import publish_builtin_skill

__all__ = ["run"]

# "variant" columns hold arbitrary JSON (ai_context is a string or an object, expressions and
# custom_extensions are lists of objects, unique_keys is a list of lists). BigQuery stores them as
# native JSON; other destinations store them as they did before. "array" columns are string lists.
OSI_MODEL = TableSchema(
    "AGENTS.OSI_MODEL",
    (
        Column("name", "varchar", nullable=False),
        Column("version", "varchar"),
        Column("description", "text"),
        Column("synonyms", "array"),
        Column("ai_context", "variant"),
        Column("custom_extensions", "variant"),
    ),
    primary_key=("name",),
)
OSI_DATASET = TableSchema(
    "AGENTS.OSI_DATASET",
    (
        Column("model_name", "varchar", nullable=False),
        Column("name", "varchar", nullable=False),
        Column("source", "varchar", nullable=False),
        Column("primary_key", "array"),
        Column("unique_keys", "variant"),
        Column("description", "text"),
        Column("synonyms", "array"),
        Column("ai_context", "variant"),
        Column("custom_extensions", "variant"),
    ),
    primary_key=("model_name", "name"),
)
OSI_FIELD = TableSchema(
    "AGENTS.OSI_FIELD",
    (
        Column("dataset_name", "varchar", nullable=False),
        Column("name", "varchar", nullable=False),
        Column("label", "varchar"),
        Column("description", "text"),
        Column("is_time_dimension", "boolean"),
        Column("expressions", "variant"),
        Column("synonyms", "array"),
        Column("ai_context", "variant"),
        Column("custom_extensions", "variant"),
    ),
    primary_key=("dataset_name", "name"),
)
OSI_METRIC = TableSchema(
    "AGENTS.OSI_METRIC",
    (
        Column("model_name", "varchar", nullable=False),
        Column("name", "varchar", nullable=False),
        Column("description", "text"),
        Column("expressions", "variant"),
        Column("synonyms", "array"),
        Column("ai_context", "variant"),
        Column("custom_extensions", "variant"),
    ),
    primary_key=("model_name", "name"),
)
OSI_RELATIONSHIP = TableSchema(
    "AGENTS.OSI_RELATIONSHIP",
    (
        Column("model_name", "varchar", nullable=False),
        Column("name", "varchar", nullable=False),
        Column("from_dataset", "varchar", nullable=False),
        Column("to_dataset", "varchar", nullable=False),
        Column("from_columns", "array", nullable=False),
        Column("to_columns", "array", nullable=False),
        Column("synonyms", "array"),
        Column("ai_context", "variant"),
        Column("custom_extensions", "variant"),
    ),
    primary_key=("model_name", "name"),
)

_TABLES = (OSI_MODEL, OSI_DATASET, OSI_FIELD, OSI_METRIC, OSI_RELATIONSHIP)
_SCHEMA = json.loads((resources.files("agents_schema") / "osi-schema.json").read_text())


def run(cfg: dict) -> None:
    osi_dir = Path(cfg["metadata_connection"]["path"])
    docs = _load_osi_files(osi_dir)
    rows = _collect(docs)  # parse first: nothing is written to the warehouse unless every file is usable
    with open_destination(cfg) as dest:
        upsert_provider_root(dest, "osi")
        _create_tables(dest)
        _write(dest, rows)
        publish_builtin_skill(dest, warehouse_type(cfg))


def _load_osi_files(osi_dir: Path) -> list[dict]:
    files = sorted(osi_dir.glob("*.osi.yaml"))
    if not files:
        raise FileNotFoundError(f"no *.osi.yaml files found in {osi_dir}")
    docs = []
    for f in files:
        try:
            doc = yaml.safe_load(f.read_text())
        except (yaml.YAMLError, ValueError) as e:
            raise ValueError(f"{f}: invalid YAML: {e}") from e
        _validate(doc, f)
        docs.append(doc)
    return docs


def _validate(doc: Any, path: Path) -> None:
    supported = _SCHEMA["properties"]["version"].get("const")
    version = doc.get("version") if isinstance(doc, dict) else None
    if supported and version is not None and version != supported:
        raise ValueError(
            f"{path}: unsupported OSI version {version!r}; this release of agents-schema reads OSI {supported}"
        )
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
    _write(dest, _collect(docs))


def _collect(docs: list[dict]) -> tuple[list, list, list, list, list]:
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

    return models, datasets, fields, metrics, relationships


def _write(dest: Destination, rows: tuple[list, list, list, list, list]) -> None:
    for table, table_rows in zip(_TABLES, rows):
        if table_rows:
            dest.insert_rows(table, table_rows)

    models, datasets, fields, metrics, relationships = rows
    print(
        f"  osi:      {len(models)} models, {len(datasets)} datasets, {len(fields)} fields, "
        f"{len(metrics)} metrics, {len(relationships)} relationships"
    )
