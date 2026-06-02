"""OpenMetadata connector: writes agents.openmetadata* from metadata exports."""
from __future__ import annotations

from typing import Any

from .destinations import Column, TableSchema
from .metadata_helpers import (
    _bool,
    _description,
    _dicts,
    _identifier,
    _name,
    _owner_name,
    _pick,
    _platform,
    _records,
    _rows,
    _summarize,
    _text,
    run_connector,
)

__all__ = ["run"]

OPENMETADATA_ENTITY = TableSchema(
    "agents.openmetadata_entity",
    (
        Column("fully_qualified_name", "varchar", nullable=False),
        Column("entity_type", "varchar"),
        Column("name", "varchar"),
        Column("description", "text"),
        Column("owner_name", "varchar"),
    ),
    primary_key=("fully_qualified_name",),
)
OPENMETADATA_FIELD = TableSchema(
    "agents.openmetadata_field",
    (
        Column("entity_fqn", "varchar", nullable=False),
        Column("field_name", "varchar", nullable=False),
        Column("data_type", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("entity_fqn", "field_name"),
)
OPENMETADATA_LINEAGE = TableSchema(
    "agents.openmetadata_lineage",
    (
        Column("upstream_fqn", "varchar", nullable=False),
        Column("downstream_fqn", "varchar", nullable=False),
        Column("relationship_type", "varchar"),
    ),
    primary_key=("upstream_fqn", "downstream_fqn"),
)

TABLES = (OPENMETADATA_ENTITY, OPENMETADATA_FIELD, OPENMETADATA_LINEAGE)
SUMMARY = _summarize("openmeta:", ((OPENMETADATA_ENTITY, "entities"), (OPENMETADATA_FIELD, "fields"), (OPENMETADATA_LINEAGE, "lineage edges")))


def run(cfg: dict[str, Any]) -> None:
    run_connector(cfg, "openmetadata", TABLES, _openmetadata_parse, SUMMARY)


def _openmetadata_parse(documents: list[Any]) -> dict[TableSchema, list[tuple[Any, ...]]]:
    tables = (OPENMETADATA_ENTITY, OPENMETADATA_FIELD, OPENMETADATA_LINEAGE)
    rows = _rows(tables)
    for entity in _records(documents, "data", "entities"):
        fqn = _text(_pick(entity, "fullyQualifiedName", "fqn", "id"))
        if not fqn:
            continue
        rows[OPENMETADATA_ENTITY].append((
            fqn,
            _text(_pick(entity, "entityType", "type")),
            _name(entity),
            _description(entity),
            _owner_name(entity),
        ))
        for column in _dicts(_pick(entity, "columns", "fields", default=[])):
            column_name = _name(column)
            if column_name:
                rows[OPENMETADATA_FIELD].append((
                    fqn,
                    column_name,
                    _text(_pick(column, "dataType", "type")),
                    _description(column),
                ))
        lineage = _pick(entity, "lineage", default={})
        for upstream in _dicts(_pick(lineage, "upstreamEdges", "upstream", default=[]) if isinstance(lineage, dict) else []):
            upstream_fqn = _text(_pick(upstream, "fullyQualifiedName", "fromEntity", "fromFqn"))
            if upstream_fqn:
                rows[OPENMETADATA_LINEAGE].append((upstream_fqn, fqn, _text(_pick(upstream, "lineageDetails", "type"))))
    return rows
