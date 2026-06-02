"""Collibra connector: writes agents.collibra* from metadata exports."""
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

COLLIBRA_ASSET = TableSchema(
    "agents.collibra_asset",
    (
        Column("asset_id", "varchar", nullable=False),
        Column("name", "varchar"),
        Column("display_name", "varchar"),
        Column("asset_type", "varchar"),
        Column("domain_id", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("asset_id",),
)
COLLIBRA_ATTRIBUTE = TableSchema(
    "agents.collibra_attribute",
    (
        Column("asset_id", "varchar", nullable=False),
        Column("attribute_type", "varchar", nullable=False),
        Column("value", "text"),
    ),
    primary_key=("asset_id", "attribute_type"),
)
COLLIBRA_RELATION = TableSchema(
    "agents.collibra_relation",
    (
        Column("source_asset_id", "varchar", nullable=False),
        Column("target_asset_id", "varchar", nullable=False),
        Column("relation_type", "varchar"),
    ),
    primary_key=("source_asset_id", "target_asset_id"),
)
COLLIBRA_RESPONSIBILITY = TableSchema(
    "agents.collibra_responsibility",
    (
        Column("asset_id", "varchar", nullable=False),
        Column("owner_id", "varchar", nullable=False),
        Column("role", "varchar"),
    ),
    primary_key=("asset_id", "owner_id"),
)

TABLES = (COLLIBRA_ASSET, COLLIBRA_ATTRIBUTE, COLLIBRA_RELATION, COLLIBRA_RESPONSIBILITY)
SUMMARY = _summarize("collibra:", ((COLLIBRA_ASSET, "assets"), (COLLIBRA_RELATION, "relations"), (COLLIBRA_RESPONSIBILITY, "responsibilities")))


def run(cfg: dict[str, Any]) -> None:
    run_connector(cfg, "collibra", TABLES, _collibra_parse, SUMMARY)


def _collibra_parse(documents: list[Any]) -> dict[TableSchema, list[tuple[Any, ...]]]:
    tables = (COLLIBRA_ASSET, COLLIBRA_ATTRIBUTE, COLLIBRA_RELATION, COLLIBRA_RESPONSIBILITY)
    rows = _rows(tables)
    for asset in _records(documents, "assets", "results"):
        asset_id = _identifier(asset, "id", "assetId")
        if not asset_id:
            continue
        rows[COLLIBRA_ASSET].append((
            asset_id,
            _name(asset),
            _text(_pick(asset, "displayName", "display_name")),
            _text(_pick(asset.get("type", {}) if isinstance(asset.get("type"), dict) else asset, "name", "assetType")),
            _text(_pick(asset.get("domain", {}) if isinstance(asset.get("domain"), dict) else {}, "id")),
            _description(asset),
        ))
        for attr in _dicts(_pick(asset, "attributes", default=[])):
            attr_type = _text(_pick(attr.get("type", {}) if isinstance(attr.get("type"), dict) else attr, "name", "attributeType"))
            if attr_type:
                rows[COLLIBRA_ATTRIBUTE].append((asset_id, attr_type, _text(_pick(attr, "value", "text"))))
        for relation in _dicts(_pick(asset, "relations", "relationships", default=[])):
            target = _text(_pick(relation, "targetId", "target", "to"))
            source = _text(_pick(relation, "sourceId", "source", "from")) or asset_id
            if source and target:
                rows[COLLIBRA_RELATION].append((source, target, _text(_pick(relation, "type", "relationType"))))
        for responsibility in _dicts(_pick(asset, "responsibilities", "owners", default=[])):
            owner_id = _text(_pick(responsibility, "ownerId", "userId", "id"))
            if owner_id:
                rows[COLLIBRA_RESPONSIBILITY].append((asset_id, owner_id, _text(_pick(responsibility, "role", "type"))))
    return rows
