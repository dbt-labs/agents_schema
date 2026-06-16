from __future__ import annotations

import re
from typing import Any, Iterable

from agents_schema.config import ConfigError

from .base import AgentsSchemaWriter
from .schema import AGENTS_SCHEMA, Column, TableSchema
from .utils import batched, bind_json_array_rows, databricks_placeholder, flatten, primary_key_rows

BATCH_SIZE = 1000
DATABRICKS_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


class DatabricksAgentsSchemaWriter(AgentsSchemaWriter):
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def ensure_table(self, table: TableSchema) -> None:
        self._execute(f"CREATE SCHEMA IF NOT EXISTS {AGENTS_SCHEMA}")
        self._execute(
            f"CREATE TABLE IF NOT EXISTS {self._table_ref(table)} "
            f"({self._column_definitions(table)})"
        )

    def replace_table(self, table: TableSchema) -> None:
        self._execute(f"CREATE SCHEMA IF NOT EXISTS {AGENTS_SCHEMA}")
        self._execute(
            f"CREATE OR REPLACE TABLE {self._table_ref(table)} "
            f"({self._column_definitions(table)})"
        )

    def delete_rows(
        self,
        table: TableSchema,
        key_columns: tuple[str, ...],
        rows: Iterable[tuple[Any, ...]],
    ) -> None:
        if not key_columns:
            raise ConfigError("delete requires at least one key column")
        bind_rows = list(rows)
        if not bind_rows:
            return
        self.ensure_table(table)
        with self._connection.cursor() as cursor:
            for row in bind_rows:
                where_sql = " AND ".join(f"{self._identifier(column)} = ?" for column in key_columns)
                cursor.execute(f"DELETE FROM {self._table_ref(table)} WHERE {where_sql}", list(row))

    def insert_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None:
        bind_rows = bind_json_array_rows(table, list(rows))
        if not bind_rows:
            return
        with self._connection.cursor() as cursor:
            for batch in batched(bind_rows, BATCH_SIZE):
                cursor.execute(self._insert_sql(table, len(batch)), list(flatten(batch)))

    def upsert_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None:
        self.ensure_table(table)
        bind_rows = bind_json_array_rows(table, list(rows))
        if not bind_rows:
            return
        with self._connection.cursor() as cursor:
            for batch in batched(bind_rows, BATCH_SIZE):
                cursor.execute(self._merge_sql(table, len(batch)), list(flatten(batch)))

    def reconcile_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None:
        rows = list(rows)
        self.ensure_table(table)
        self.upsert_rows(table, rows)
        self._delete_absent_rows(table, primary_key_rows(table, rows))

    def close(self) -> None:
        self._connection.close()

    def _execute(self, sql: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(sql)

    def _table_ref(self, table: TableSchema) -> str:
        return f"{self._identifier(AGENTS_SCHEMA)}.{self._identifier(table.base_name)}"

    def _identifier(self, identifier: str) -> str:
        if not DATABRICKS_IDENTIFIER_RE.fullmatch(identifier):
            raise ConfigError(f"expected a simple Databricks identifier: {identifier}")
        return f"`{identifier}`"

    def _column_definitions(self, table: TableSchema) -> str:
        return ", ".join(
            f"{self._identifier(column.name)} {_databricks_type(column)}"
            f"{' NOT NULL' if not column.nullable else ''}"
            for column in table.columns
        )

    def _insert_sql(self, table: TableSchema, row_count: int) -> str:
        columns = ", ".join(self._identifier(column.name) for column in table.columns)
        row_placeholders = ", ".join(
            "(" + ", ".join(databricks_placeholder(column) for column in table.columns) + ")"
            for _ in range(row_count)
        )
        return f"INSERT INTO {self._table_ref(table)} ({columns}) VALUES {row_placeholders}"

    def _merge_sql(self, table: TableSchema, row_count: int) -> str:
        if not table.primary_key:
            raise ConfigError("upsert requires a table primary key")
        columns = [column.name for column in table.columns]
        non_key_columns = [column for column in columns if column not in table.primary_key]
        row_selects = []
        for _ in range(row_count):
            row_selects.append(
                "SELECT "
                + ", ".join(
                    f"{databricks_placeholder(column)} AS {self._identifier(column.name)}"
                    for column in table.columns
                )
            )
        source_sql = " UNION ALL ".join(row_selects)
        on_sql = " AND ".join(
            f"target.{self._identifier(column)} = source.{self._identifier(column)}"
            for column in table.primary_key
        )
        update_sql = ", ".join(
            f"target.{self._identifier(column)} = source.{self._identifier(column)}"
            for column in non_key_columns
        )
        insert_columns = ", ".join(self._identifier(column) for column in columns)
        insert_values = ", ".join(f"source.{self._identifier(column)}" for column in columns)
        matched_sql = f"WHEN MATCHED THEN UPDATE SET {update_sql}\n" if update_sql else ""
        return (
            f"MERGE INTO {self._table_ref(table)} AS target\n"
            f"USING ({source_sql}) AS source\n"
            f"ON {on_sql}\n"
            f"{matched_sql}"
            f"WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values})"
        )

    def _delete_absent_rows(self, table: TableSchema, key_rows: list[tuple[Any, ...]]) -> None:
        with self._connection.cursor() as cursor:
            if not key_rows:
                cursor.execute(f"DELETE FROM {self._table_ref(table)}")
                return
            source_sql = " UNION ALL ".join(
                "SELECT " + ", ".join(f"? AS {self._identifier(column)}" for column in table.primary_key)
                for _ in key_rows
            )
            exists_sql = " AND ".join(
                f"target.{self._identifier(column)} = source.{self._identifier(column)}"
                for column in table.primary_key
            )
            cursor.execute(
                f"DELETE FROM {self._table_ref(table)} AS target\n"
                f"WHERE NOT EXISTS (\n"
                f"    SELECT 1 FROM ({source_sql}) AS source\n"
                f"    WHERE {exists_sql}\n"
                f")",
                list(flatten(key_rows)),
            )


def _databricks_type(column: Column) -> str:
    if column.kind == "array":
        return "ARRAY<STRING>"
    if column.kind == "boolean":
        return "BOOLEAN"
    if column.kind in {"text", "varchar"}:
        return "STRING"
    raise ValueError(f"unsupported column kind: {column.kind}")
