"""Memory connector: writes durable agent memories from YAML.

Memory is the lightweight path to anchored, agent-retrievable notes for
deployments without a semantic layer. A team running OSI already has
object-local `ai_context` and rarely needs this; see SPEC.md "Source: Memory".

Naming follows the OSI parent/child convention: the entity table's own key is
``AGENTS.MEMORY.memory_id`` and child rows reference it with the same prefixed
name (``AGENTS.MEMORY_ANCHOR.memory_id``), mirroring
``OSI_DATASET.name`` / ``OSI_FIELD.dataset_name``.
"""
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
        Column("confidence", "float"),
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
        Column("metric_id", "varchar"),
        Column("relationship_name", "varchar"),
        Column("from_schema", "varchar"),
        Column("from_table", "varchar"),
        Column("from_columns", "array"),
        Column("to_schema", "varchar"),
        Column("to_table", "varchar"),
        Column("to_columns", "array"),
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
    "metric_id",
    "relationship_name",
    "from_schema",
    "from_table",
    "from_columns",
    "to_schema",
    "to_table",
    "to_columns",
)

# Locator columns hold the join/relationship arrays; everything else is scalar.
ANCHOR_ARRAY_FIELDS = frozenset({"from_columns", "to_columns"})

TOP_LEVEL_FIELDS = frozenset({"memories"})
MEMORY_FIELD_SET = frozenset(MEMORY_FIELDS) | {"anchors"}
ANCHOR_FIELD_SET = frozenset(ANCHOR_FIELDS) - {"memory_id"}
STRING_MEMORY_FIELDS = frozenset(MEMORY_FIELDS) - {"confidence"}
STRING_ANCHOR_FIELDS = frozenset(ANCHOR_FIELDS) - {"memory_id"} - ANCHOR_ARRAY_FIELDS
ANCHOR_TYPES = frozenset({"column", "table", "relationship", "metric"})

# Which locator columns each anchor type is allowed to set. Anything outside the
# allowed set for a type is rejected so rows stay clean and unambiguous.
ALL_LOCATORS = frozenset(ANCHOR_FIELD_SET - {"anchor_id", "anchor_type"})
ALLOWED_LOCATORS = {
    "column": frozenset({"schema_name", "table_name", "column_name"}),
    "table": frozenset({"schema_name", "table_name"}),
    "metric": frozenset({"metric_id"}),
    "relationship": frozenset(
        {
            "relationship_name",
            "from_schema",
            "from_table",
            "from_columns",
            "to_schema",
            "to_table",
            "to_columns",
        }
    ),
}


def run(cfg: dict) -> None:
    memory_file = Path(cfg["metadata_connection"]["path"])
    memories, anchors = load_memory_file(memory_file)
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
        memory_loc = f"memories[{index}]"
        if not isinstance(raw_memory, dict):
            raise ConfigError(f"{memory_loc} must be an object")
        _reject_unknown_fields(raw_memory, MEMORY_FIELD_SET, memory_loc)
        _validate_strings(raw_memory, STRING_MEMORY_FIELDS, memory_loc)
        _validate_confidence(raw_memory, memory_loc)
        memory_id = _required_str(raw_memory, "memory_id", memory_loc)
        _required_str(raw_memory, "memory_kind", memory_loc)
        _required_str(raw_memory, "content", memory_loc)
        if memory_id in seen_memories:
            raise ConfigError(f"duplicate memory: {memory_id}")
        seen_memories.add(memory_id)
        memory_rows.append(tuple(raw_memory.get(field) for field in MEMORY_FIELDS))

        raw_anchors = raw_memory.get("anchors", [])
        if not isinstance(raw_anchors, list):
            raise ConfigError(f"{memory_loc}.anchors must be a list")
        for anchor_index, raw_anchor in enumerate(raw_anchors):
            anchor_loc = f"{memory_loc}.anchors[{anchor_index}]"
            if not isinstance(raw_anchor, dict):
                raise ConfigError(f"{anchor_loc} must be an object")
            _reject_unknown_fields(raw_anchor, ANCHOR_FIELD_SET, anchor_loc)
            _validate_strings(raw_anchor, STRING_ANCHOR_FIELDS, anchor_loc)
            for field in ANCHOR_ARRAY_FIELDS:
                _validate_string_list(raw_anchor, field, anchor_loc)
            anchor_id = _required_str(raw_anchor, "anchor_id", anchor_loc)
            anchor_type = _required_str(raw_anchor, "anchor_type", anchor_loc)
            if anchor_type not in ANCHOR_TYPES:
                raise ConfigError(f"{anchor_loc}.anchor_type is not supported: {anchor_type}")
            _validate_anchor_locator(raw_anchor, anchor_loc, anchor_type)
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


def _validate_confidence(data: dict[str, Any], path: str) -> None:
    value = data.get("confidence")
    if value is None:
        return
    # bool is a subclass of int; reject it explicitly so True/False is not stored as 1.0/0.0.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{path}.confidence must be a number")
    if not 0.0 <= float(value) <= 1.0:
        raise ConfigError(f"{path}.confidence must be between 0 and 1")


def _validate_string_list(data: dict[str, Any], field: str, path: str) -> None:
    value = data.get(field)
    if value is None:
        return
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ConfigError(f"{path}.{field} must be a list of strings")


def _validate_anchor_locator(anchor: dict[str, Any], path: str, anchor_type: str) -> None:
    disallowed = sorted(field for field in ALL_LOCATORS - ALLOWED_LOCATORS[anchor_type] if anchor.get(field))
    if disallowed:
        raise ConfigError(f"{path}: {anchor_type} anchors do not use {disallowed[0]}")

    if anchor_type == "column":
        if not anchor.get("table_name") or not anchor.get("column_name"):
            raise ConfigError(f"{path}: column anchors require table_name and column_name")
    elif anchor_type == "table":
        if not anchor.get("table_name"):
            raise ConfigError(f"{path}: table anchors require table_name")
    elif anchor_type == "metric":
        if not anchor.get("metric_id"):
            raise ConfigError(f"{path}: metric anchors require metric_id")
    elif anchor_type == "relationship":
        _validate_relationship_locator(anchor, path)


def _validate_relationship_locator(anchor: dict[str, Any], path: str) -> None:
    if not anchor.get("from_table") or not anchor.get("to_table"):
        raise ConfigError(f"{path}: relationship anchors require from_table and to_table")
    from_columns = anchor.get("from_columns")
    to_columns = anchor.get("to_columns")
    if bool(from_columns) != bool(to_columns):
        raise ConfigError(f"{path}: relationship anchors need from_columns and to_columns together")
    if from_columns and len(from_columns) != len(to_columns):
        raise ConfigError(f"{path}: from_columns and to_columns must be the same length")
