"""Alation connector: writes agents.alation* from metadata exports."""
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

ALATION_DATA_SOURCE = TableSchema(
    "agents.alation_data_source",
    (
        Column("data_source_id", "varchar", nullable=False),
        Column("title", "varchar"),
        Column("description", "text"),
        Column("dbtype", "varchar"),
    ),
    primary_key=("data_source_id",),
)
ALATION_TABLE = TableSchema(
    "agents.alation_table",
    (
        Column("table_id", "varchar", nullable=False),
        Column("data_source_id", "varchar"),
        Column("schema_name", "varchar"),
        Column("name", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("table_id",),
)
ALATION_COLUMN = TableSchema(
    "agents.alation_column",
    (
        Column("column_id", "varchar", nullable=False),
        Column("table_id", "varchar"),
        Column("name", "varchar"),
        Column("data_type", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("column_id",),
)
ALATION_GLOSSARY_TERM = TableSchema(
    "agents.alation_glossary_term",
    (
        Column("term_id", "varchar", nullable=False),
        Column("title", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("term_id",),
)

TABLES = (ALATION_DATA_SOURCE, ALATION_TABLE, ALATION_COLUMN, ALATION_GLOSSARY_TERM)
SUMMARY = _summarize("alation:", ((ALATION_DATA_SOURCE, "sources"), (ALATION_TABLE, "tables"), (ALATION_GLOSSARY_TERM, "terms")))


def run(cfg: dict[str, Any]) -> None:
    run_connector(cfg, "alation", TABLES, _alation_parse, SUMMARY)


def _alation_parse(documents: list[Any]) -> dict[TableSchema, list[tuple[Any, ...]]]:
    tables = (ALATION_DATA_SOURCE, ALATION_TABLE, ALATION_COLUMN, ALATION_GLOSSARY_TERM)
    rows = _rows(tables)
    for data_source in _records(documents, "data_sources", "dataSources"):
        data_source_id = _identifier(data_source, "id", "ds_id")
        if data_source_id:
            rows[ALATION_DATA_SOURCE].append((
                data_source_id,
                _text(_pick(data_source, "title", "name")),
                _description(data_source),
                _text(_pick(data_source, "dbtype", "type")),
            ))
    for table in _records(documents, "tables"):
        table_id = _identifier(table, "id", "table_id")
        if table_id:
            rows[ALATION_TABLE].append((
                table_id,
                _text(_pick(table, "ds_id", "data_source_id")),
                _text(_pick(table, "schema_name", "schema")),
                _name(table),
                _description(table),
            ))
        for column in _dicts(table.get("columns")):
            column_id = _identifier(column, "id", "column_id") or f"{table_id}.{_name(column)}"
            if table_id and column_id:
                rows[ALATION_COLUMN].append((
                    column_id,
                    table_id,
                    _name(column),
                    _text(_pick(column, "data_type", "type")),
                    _description(column),
                ))
    for column in _records(documents, "columns"):
        column_id = _identifier(column, "id", "column_id")
        if column_id:
            rows[ALATION_COLUMN].append((
                column_id,
                _text(_pick(column, "table_id")),
                _name(column),
                _text(_pick(column, "data_type", "type")),
                _description(column),
            ))
    for term in _records(documents, "glossary_terms", "terms"):
        term_id = _identifier(term, "id", "term_id")
        if term_id:
            rows[ALATION_GLOSSARY_TERM].append((term_id, _text(_pick(term, "title", "name")), _description(term)))
    return rows
