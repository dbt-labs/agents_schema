from __future__ import annotations

import json
from typing import Any, Iterable

from .schema import Column, TableSchema


def bind_json_array_rows(table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    bind_rows = []
    for row in rows:
        bind_row = []
        for index, value in enumerate(row):
            if index in table.array_indexes:
                bind_row.append(json.dumps(value or []))
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


def databricks_placeholder(column: Column) -> str:
    if column.kind == "array":
        return "from_json(?, 'array<string>')"
    return "?"
