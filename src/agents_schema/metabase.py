"""Metabase connector: writes agents.metabase* from metadata exports."""
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

METABASE_DATABASE = TableSchema(
    "agents.metabase_database",
    (
        Column("database_id", "varchar", nullable=False),
        Column("name", "varchar"),
        Column("engine", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("database_id",),
)
METABASE_TABLE = TableSchema(
    "agents.metabase_table",
    (
        Column("table_id", "varchar", nullable=False),
        Column("database_id", "varchar"),
        Column("schema_name", "varchar"),
        Column("name", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("table_id",),
)
METABASE_FIELD = TableSchema(
    "agents.metabase_field",
    (
        Column("field_id", "varchar", nullable=False),
        Column("table_id", "varchar"),
        Column("name", "varchar"),
        Column("base_type", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("field_id",),
)
METABASE_CARD = TableSchema(
    "agents.metabase_card",
    (
        Column("card_id", "varchar", nullable=False),
        Column("database_id", "varchar"),
        Column("name", "varchar"),
        Column("description", "text"),
        Column("dataset_query", "array"),
    ),
    primary_key=("card_id",),
)
METABASE_DASHBOARD = TableSchema(
    "agents.metabase_dashboard",
    (
        Column("dashboard_id", "varchar", nullable=False),
        Column("name", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("dashboard_id",),
)

TABLES = (METABASE_DATABASE, METABASE_TABLE, METABASE_FIELD, METABASE_CARD, METABASE_DASHBOARD)
SUMMARY = _summarize("metabase:", ((METABASE_DATABASE, "databases"), (METABASE_CARD, "cards"), (METABASE_DASHBOARD, "dashboards")))


def run(cfg: dict[str, Any]) -> None:
    run_connector(cfg, "metabase", TABLES, _metabase_parse, SUMMARY)


def _metabase_parse(documents: list[Any]) -> dict[TableSchema, list[tuple[Any, ...]]]:
    tables = (METABASE_DATABASE, METABASE_TABLE, METABASE_FIELD, METABASE_CARD, METABASE_DASHBOARD)
    rows = _rows(tables)
    for database in _records(documents, "databases"):
        database_id = _identifier(database, "id", "database_id")
        if database_id:
            rows[METABASE_DATABASE].append((database_id, _name(database), _text(database.get("engine")), _description(database)))
        for table in _dicts(database.get("tables")):
            _append_metabase_table(rows, table, database_id)
    for table in _records(documents, "tables"):
        _append_metabase_table(rows, table, _text(_pick(table, "db_id", "database_id")))
    for card in _records(documents, "cards", "questions"):
        card_id = _identifier(card, "id", "card_id")
        if card_id:
            rows[METABASE_CARD].append((
                card_id,
                _text(_pick(card, "database_id", "db_id")),
                _name(card),
                _description(card),
                _pick(card, "dataset_query", "query", default={}),
            ))
    for dashboard in _records(documents, "dashboards"):
        dashboard_id = _identifier(dashboard, "id", "dashboard_id")
        if dashboard_id:
            rows[METABASE_DASHBOARD].append((dashboard_id, _name(dashboard), _description(dashboard)))
    return rows


def _append_metabase_table(rows: dict[TableSchema, list[tuple[Any, ...]]], table: dict[str, Any], database_id: str | None) -> None:
    table_id = _identifier(table, "id", "table_id")
    if not table_id:
        return
    rows[METABASE_TABLE].append((
        table_id,
        database_id,
        _text(_pick(table, "schema", "schema_name")),
        _name(table),
        _description(table),
    ))
    for field in _dicts(table.get("fields")):
        field_id = _identifier(field, "id", "field_id") or f"{table_id}.{_name(field)}"
        if field_id:
            rows[METABASE_FIELD].append((
                field_id,
                table_id,
                _name(field),
                _text(_pick(field, "base_type", "semantic_type", "type")),
                _description(field),
            ))
