from __future__ import annotations

import json
from typing import Any, Iterable

from agents_schema.config import ConfigError

from .schema import Column, RowScope, TableSchema


def bind_json_rows(table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    bind_rows = []
    for row in rows:
        bind_row = []
        for index, value in enumerate(row):
            if index in table.array_indexes:
                bind_row.append(json.dumps(value or []))
            elif index in table.json_indexes:
                bind_row.append(json.dumps(value or {}))
            else:
                bind_row.append(value)
        bind_rows.append(tuple(bind_row))
    return bind_rows


def batched(rows: list[tuple[Any, ...]], size: int) -> Iterable[list[tuple[Any, ...]]]:
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def flatten(rows: list[tuple[Any, ...]]) -> tuple[Any, ...]:
    return tuple(value for row in rows for value in row)


def primary_key_rows(table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    primary_key_indexes = [
        index for index, column in enumerate(table.columns) if column.name in table.primary_key
    ]
    return [tuple(row[index] for index in primary_key_indexes) for row in rows]


def scope_terms(scope: RowScope | None) -> list[tuple[str, str, str]]:
    """Flatten a scope into (kind, column, value) terms; kind is "eq" or "prefix"."""
    if scope is None:
        return []
    return [("eq", column, value) for column, value in scope.equals] + [
        ("prefix", column, value) for column, value in scope.starts_with
    ]


def check_rows_in_scope(table: TableSchema, rows: list[tuple[Any, ...]], scope: RowScope | None) -> None:
    """Refuse rows outside the scope: they would be upserted but could never be reconciled away."""
    terms = scope_terms(scope)
    if not terms:
        return
    names = [column.name for column in table.columns]
    for row in rows:
        for kind, column, value in terms:
            actual = row[names.index(column)]
            inside = actual == value if kind == "eq" else isinstance(actual, str) and actual.startswith(value)
            if not inside:
                raise ConfigError(f"{table.base_name}: row {row[:2]} is outside the reconcile scope ({column} {kind} {value!r})")


def rows_json_for_table(table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> list[dict[str, Any]]:
    return [
        {column.name: value for column, value in zip(table.columns, row, strict=True)}
        for row in rows
    ]


def databricks_placeholder(column: Column) -> str:
    if column.kind == "array":
        return "from_json(?, 'array<string>')"
    if column.kind in {"json", "variant"}:
        return "parse_json(?)"
    return "?"
