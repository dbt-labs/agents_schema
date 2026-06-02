"""DataHub connector: writes agents.datahub* from metadata exports."""
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

DATAHUB_ENTITY = TableSchema(
    "agents.datahub_entity",
    (
        Column("urn", "varchar", nullable=False),
        Column("entity_type", "varchar"),
        Column("platform", "varchar"),
        Column("name", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("urn",),
)
DATAHUB_FIELD = TableSchema(
    "agents.datahub_field",
    (
        Column("entity_urn", "varchar", nullable=False),
        Column("field_path", "varchar", nullable=False),
        Column("native_data_type", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("entity_urn", "field_path"),
)
DATAHUB_OWNER = TableSchema(
    "agents.datahub_owner",
    (
        Column("entity_urn", "varchar", nullable=False),
        Column("owner_urn", "varchar", nullable=False),
        Column("ownership_type", "varchar"),
    ),
    primary_key=("entity_urn", "owner_urn"),
)
DATAHUB_LINEAGE = TableSchema(
    "agents.datahub_lineage",
    (
        Column("upstream_urn", "varchar", nullable=False),
        Column("downstream_urn", "varchar", nullable=False),
        Column("relationship_type", "varchar"),
    ),
    primary_key=("upstream_urn", "downstream_urn"),
)

TABLES = (DATAHUB_ENTITY, DATAHUB_FIELD, DATAHUB_OWNER, DATAHUB_LINEAGE)
SUMMARY = _summarize("datahub:", ((DATAHUB_ENTITY, "entities"), (DATAHUB_FIELD, "fields"), (DATAHUB_LINEAGE, "lineage edges")))


def run(cfg: dict[str, Any]) -> None:
    run_connector(cfg, "datahub", TABLES, _datahub_parse, SUMMARY)


def _datahub_parse(documents: list[Any]) -> dict[TableSchema, list[tuple[Any, ...]]]:
    tables = (DATAHUB_ENTITY, DATAHUB_FIELD, DATAHUB_OWNER, DATAHUB_LINEAGE)
    rows = _rows(tables)
    for raw_entity in _records(documents, "entities", "searchResults"):
        entity = raw_entity.get("entity") if isinstance(raw_entity.get("entity"), dict) else raw_entity
        urn = _text(_pick(entity, "urn"))
        if not urn:
            continue
        schema = _pick(entity, "schemaMetadata", default={})
        props = _pick(entity, "properties", "editableProperties", default={})
        rows[DATAHUB_ENTITY].append((
            urn,
            _text(_pick(entity, "type", "entityType")),
            _platform(entity),
            _name(props) or _name(entity),
            _description(props) or _description(entity),
        ))
        if isinstance(schema, dict):
            for field in _dicts(schema.get("fields")):
                field_path = _text(_pick(field, "fieldPath", "name"))
                if field_path:
                    rows[DATAHUB_FIELD].append((
                        urn,
                        field_path,
                        _text(_pick(field, "nativeDataType", "type")),
                        _description(field),
                    ))
        ownership = _pick(entity, "ownership", default={})
        for owner in _dicts(ownership.get("owners") if isinstance(ownership, dict) else []):
            owner_urn = _text(_pick(owner, "ownerUrn", "owner"))
            if owner_urn:
                rows[DATAHUB_OWNER].append((urn, owner_urn, _text(_pick(owner, "type", "ownershipType"))))
        lineage = _pick(entity, "upstreamLineage", "lineage", default={})
        upstreams = lineage.get("upstreams") if isinstance(lineage, dict) else []
        for upstream in _dicts(upstreams):
            upstream_urn = _text(_pick(upstream, "dataset", "urn", "upstreamUrn"))
            if upstream_urn:
                rows[DATAHUB_LINEAGE].append((upstream_urn, urn, _text(_pick(upstream, "type", "relationshipType"))))
    return rows
