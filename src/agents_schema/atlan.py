"""Atlan connector: writes agents.atlan* from metadata exports."""
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

ATLAN_ASSET = TableSchema(
    "agents.atlan_asset",
    (
        Column("guid", "varchar", nullable=False),
        Column("qualified_name", "varchar"),
        Column("asset_type", "varchar"),
        Column("name", "varchar"),
        Column("description", "text"),
        Column("owner_users", "array"),
    ),
    primary_key=("guid",),
)
ATLAN_FIELD = TableSchema(
    "agents.atlan_field",
    (
        Column("asset_guid", "varchar", nullable=False),
        Column("field_guid", "varchar", nullable=False),
        Column("qualified_name", "varchar"),
        Column("name", "varchar"),
        Column("data_type", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("asset_guid", "field_guid"),
)
ATLAN_LINEAGE = TableSchema(
    "agents.atlan_lineage",
    (
        Column("upstream_guid", "varchar", nullable=False),
        Column("downstream_guid", "varchar", nullable=False),
        Column("relationship_type", "varchar"),
    ),
    primary_key=("upstream_guid", "downstream_guid"),
)

TABLES = (ATLAN_ASSET, ATLAN_FIELD, ATLAN_LINEAGE)
SUMMARY = _summarize("atlan:", ((ATLAN_ASSET, "assets"), (ATLAN_FIELD, "fields"), (ATLAN_LINEAGE, "lineage edges")))


def run(cfg: dict[str, Any]) -> None:
    run_connector(cfg, "atlan", TABLES, _atlan_parse, SUMMARY)


def _atlan_parse(documents: list[Any]) -> dict[TableSchema, list[tuple[Any, ...]]]:
    tables = (ATLAN_ASSET, ATLAN_FIELD, ATLAN_LINEAGE)
    rows = _rows(tables)
    for asset in _records(documents, "entities", "assets", "records"):
        attrs = asset.get("attributes") if isinstance(asset.get("attributes"), dict) else asset
        guid = _text(_pick(asset, "guid", "id")) or _text(_pick(attrs, "guid", "qualifiedName"))
        if not guid:
            continue
        rows[ATLAN_ASSET].append((
            guid,
            _text(_pick(attrs, "qualifiedName", "qualified_name")),
            _text(_pick(asset, "typeName", "assetType") or _pick(attrs, "typeName", "assetType")),
            _name(attrs),
            _description(attrs),
            _pick(attrs, "ownerUsers", "owner_users", default=[]),
        ))
        related = asset.get("relationshipAttributes") if isinstance(asset.get("relationshipAttributes"), dict) else {}
        for field in _dicts(_pick(related, "columns", "fields", default=[]) or _pick(attrs, "columns", "fields", default=[])):
            field_attrs = field.get("attributes") if isinstance(field.get("attributes"), dict) else field
            field_guid = _text(_pick(field, "guid", "id")) or _text(_pick(field_attrs, "qualifiedName"))
            if field_guid:
                rows[ATLAN_FIELD].append((
                    guid,
                    field_guid,
                    _text(_pick(field_attrs, "qualifiedName", "qualified_name")),
                    _name(field_attrs),
                    _text(_pick(field_attrs, "dataType", "type")),
                    _description(field_attrs),
                ))
        for edge in _dicts(_pick(asset, "lineage", "upstream", default=[])):
            upstream = _text(_pick(edge, "upstreamGuid", "guid", "from"))
            downstream = _text(_pick(edge, "downstreamGuid", "to")) or guid
            if upstream and downstream:
                rows[ATLAN_LINEAGE].append((upstream, downstream, _text(_pick(edge, "type", "relationshipType"))))
    return rows
