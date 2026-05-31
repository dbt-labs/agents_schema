"""Memory connector: writes durable agent memories from YAML."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config import ConfigError
from .destinations import Column, Destination, TableSchema, open_destination
from .root import upsert_provider_root

__all__ = ["MEMORY", "MEMORY_ANCHOR", "load_memory_file", "run"]

MEMORY = TableSchema(
    "agents.memory",
    (
        Column("memory_id", "varchar", nullable=False),
        Column("memory_kind", "varchar", nullable=False),
        Column("title", "varchar"),
        Column("content", "text", nullable=False),
        Column("source", "varchar"),
        Column("confidence", "varchar"),
    ),
    primary_key=("memory_id",),
)

MEMORY_ANCHOR = TableSchema(
    "agents.memory_anchor",
    (
        Column("memory_id", "varchar", nullable=False),
        Column("anchor_id", "varchar", nullable=False),
        Column("anchor_type", "varchar", nullable=False),
        Column("schema_name", "varchar"),
        Column("table_name", "varchar"),
        Column("column_name", "varchar"),
        Column("relationship_name", "varchar"),
        Column("metric_id", "varchar"),
    ),
    primary_key=(
        "memory_id",
        "anchor_id",
    ),
)

MEMORY_FIELDS = (
    "memory_id",
    "memory_kind",
    "title",
    "content",
    "source",
    "confidence",
)

ANCHOR_FIELDS = (
    "memory_id",
    "anchor_id",
    "anchor_type",
    "schema_name",
    "table_name",
    "column_name",
    "relationship_name",
    "metric_id",
)

TOP_LEVEL_FIELDS = frozenset({"memories"})
MEMORY_FIELD_SET = frozenset(MEMORY_FIELDS) | {"anchors"}
ANCHOR_FIELD_SET = frozenset(ANCHOR_FIELDS) - {"memory_id"}
STRING_MEMORY_FIELDS = frozenset(MEMORY_FIELDS)
STRING_ANCHOR_FIELDS = frozenset(ANCHOR_FIELDS)
ANCHOR_TYPES = frozenset({"column", "table", "relationship", "metric"})


def run(cfg: dict) -> None:
    memory_path = Path(cfg["metadata_connection"]["path"])
    memories, anchors = load_memory_file(memory_path)
    with open_destination(cfg) as dest:
        upsert_provider_root(dest, "memory")
        _create_tables(dest)
        if memories:
            dest.insert_rows(MEMORY, memories)
        if anchors:
            dest.insert_rows(MEMORY_ANCHOR, anchors)
    print(f"  memory:  {len(memories)} memories, {len(anchors)} anchors")


def load_memory_file(path: Path) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"memory file is not valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError("memory file must be a YAML object")
    _reject_unknown_fields(data, TOP_LEVEL_FIELDS, "memory file")
    raw_memories = data.get("memories")
    if not isinstance(raw_memories, list):
        raise ConfigError("memories must be a list")

    memory_rows: list[tuple[Any, ...]] = []
    anchor_rows: list[tuple[Any, ...]] = []
    seen_memories: set[str] = set()
    seen_anchors: set[tuple[str, str]] = set()
    for index, raw_memory in enumerate(raw_memories):
        memory_path = f"memories[{index}]"
        if not isinstance(raw_memory, dict):
            raise ConfigError(f"{memory_path} must be an object")
        _reject_unknown_fields(raw_memory, MEMORY_FIELD_SET, memory_path)
        _validate_strings(raw_memory, STRING_MEMORY_FIELDS, memory_path)
        memory_id = _required_str(raw_memory, "memory_id", memory_path)
        _required_str(raw_memory, "memory_kind", memory_path)
        _required_str(raw_memory, "content", memory_path)
        if memory_id in seen_memories:
            raise ConfigError(f"duplicate memory: {memory_id}")
        seen_memories.add(memory_id)
        memory_rows.append(tuple(raw_memory.get(field) for field in MEMORY_FIELDS))

        raw_anchors = raw_memory.get("anchors", [])
        if not isinstance(raw_anchors, list):
            raise ConfigError(f"{memory_path}.anchors must be a list")
        for anchor_index, raw_anchor in enumerate(raw_anchors):
            anchor_path = f"{memory_path}.anchors[{anchor_index}]"
            if not isinstance(raw_anchor, dict):
                raise ConfigError(f"{anchor_path} must be an object")
            _reject_unknown_fields(raw_anchor, ANCHOR_FIELD_SET, anchor_path)
            _validate_strings(raw_anchor, STRING_ANCHOR_FIELDS, anchor_path)
            anchor_id = _required_str(raw_anchor, "anchor_id", anchor_path)
            anchor_type = _required_str(raw_anchor, "anchor_type", anchor_path)
            if anchor_type not in ANCHOR_TYPES:
                raise ConfigError(f"{anchor_path}.anchor_type is not supported: {anchor_type}")
            _validate_anchor_locator(raw_anchor, anchor_path, anchor_type)
            anchor_key = (memory_id, anchor_id)
            if anchor_key in seen_anchors:
                raise ConfigError(f"duplicate memory anchor: {memory_id}.{anchor_id}")
            seen_anchors.add(anchor_key)
            anchor = dict(raw_anchor)
            anchor["memory_id"] = memory_id
            anchor_rows.append(tuple(anchor.get(field) for field in ANCHOR_FIELDS))

    return memory_rows, anchor_rows


def _create_tables(dest: Destination) -> None:
    dest.replace_table(MEMORY)
    dest.replace_table(MEMORY_ANCHOR)


def _required_str(data: dict[str, Any], field: str, path: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{path}.{field} is required")
    return value


def _reject_unknown_fields(data: dict[str, Any], allowed: frozenset[str], path: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ConfigError(f"{path} has unknown field: {unknown[0]}")


def _validate_strings(data: dict[str, Any], fields: frozenset[str], path: str) -> None:
    for field in fields:
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            raise ConfigError(f"{path}.{field} must be a string")


def _validate_anchor_locator(anchor: dict[str, Any], path: str, anchor_type: str) -> None:
    if anchor_type == "column":
        if not anchor.get("table_name") or not anchor.get("column_name"):
            raise ConfigError(f"{path}: column anchors require table_name and column_name")
    elif anchor_type == "table":
        if not anchor.get("table_name"):
            raise ConfigError(f"{path}: table anchors require table_name")
    elif anchor_type == "relationship":
        if not anchor.get("relationship_name") and not anchor.get("table_name"):
            raise ConfigError(f"{path}: relationship anchors require relationship_name or table_name")
    elif anchor_type == "metric":
        if not anchor.get("metric_id"):
            raise ConfigError(f"{path}: metric anchors require metric_id")
