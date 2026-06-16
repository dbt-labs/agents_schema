from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from agents_schema.config import ConfigError

from .base import AgentsSchemaWriter
from .schema import AGENTS_SCHEMA, TableSchema
from .utils import batched, bind_json_array_rows, flatten, primary_key_rows

INSERT_BATCH_SIZE = 1000
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


class SnowflakeAgentsSchemaWriter(AgentsSchemaWriter):
    def __init__(self, connection: Any) -> None:
        self._con = connection

    def ensure_table(self, table: TableSchema) -> None:
        with self._con.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {AGENTS_SCHEMA}")
            cur.execute(_create_table_if_not_exists_sql(table, AGENTS_SCHEMA))

    def replace_table(self, table: TableSchema) -> None:
        with self._con.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {AGENTS_SCHEMA}")
            cur.execute(_create_table_sql(table, AGENTS_SCHEMA))

    def upsert_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None:
        bind_rows = bind_json_array_rows(table, rows)
        if not bind_rows:
            return
        with self._con.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {AGENTS_SCHEMA}")
            cur.execute(_create_table_if_not_exists_sql(table, AGENTS_SCHEMA))
            for batch in batched(bind_rows, INSERT_BATCH_SIZE):
                cur.execute(_merge_sql(table, AGENTS_SCHEMA, len(batch)), flatten(batch))

    def insert_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None:
        bind_rows = bind_json_array_rows(table, rows)
        if not bind_rows:
            return
        with self._con.cursor() as cur:
            for batch in batched(bind_rows, INSERT_BATCH_SIZE):
                cur.execute(_insert_sql(table, AGENTS_SCHEMA, len(batch)), flatten(batch))

    def delete_rows(
        self,
        table: TableSchema,
        key_columns: tuple[str, ...],
        rows: Iterable[tuple[Any, ...]],
    ) -> None:
        bind_rows = list(rows)
        if not bind_rows:
            return
        with self._con.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {AGENTS_SCHEMA}")
            cur.execute(_create_table_if_not_exists_sql(table, AGENTS_SCHEMA))
            for batch in batched(bind_rows, INSERT_BATCH_SIZE):
                cur.execute(
                    _delete_sql(table, AGENTS_SCHEMA, key_columns, len(batch)),
                    flatten(batch),
                )

    def reconcile_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None:
        rows = list(rows)
        self.ensure_table(table)
        self.upsert_rows(table, rows)
        self._delete_absent_rows(table, primary_key_rows(table, rows))

    def close(self) -> None:
        self._con.close()

    def _delete_absent_rows(self, table: TableSchema, key_rows: list[tuple[Any, ...]]) -> None:
        with self._con.cursor() as cur:
            if not key_rows:
                cur.execute(f"DELETE FROM {_table_name(table, AGENTS_SCHEMA)}")
                return
            source_columns = tuple(_column_for_delete_key(column) for column in table.primary_key)
            source_table = TableSchema(table.name, source_columns)
            source_select = _source_select_sql(source_table, len(key_rows))
            exists_sql = " AND ".join(
                f"target.{_identifier(column)} = source.{_identifier(column)}"
                for column in table.primary_key
            )
            cur.execute(
                f"DELETE FROM {_table_name(table, AGENTS_SCHEMA)} AS target\n"
                f"WHERE NOT EXISTS (\n"
                f"    SELECT 1 FROM ({source_select}) AS source\n"
                f"    WHERE {exists_sql}\n"
                f")",
                flatten(key_rows),
            )


def _column_for_delete_key(name: str):
    from .schema import Column

    return Column(name, "varchar", nullable=False)


def _insert_sql(table: TableSchema, schema: str, row_count: int) -> str:
    row_select = "SELECT " + ",".join(_placeholder(table, i) for i in range(len(table.columns)))
    values_sql = " UNION ALL ".join(row_select for _ in range(row_count))
    return f"INSERT INTO {_table_name(table, schema)} {values_sql}"


def _delete_sql(table: TableSchema, schema: str, key_columns: tuple[str, ...], row_count: int) -> str:
    if not key_columns:
        raise ConfigError("delete requires at least one key column")
    source_columns = tuple(_column_for_delete_key(name) for name in key_columns)
    source_table = TableSchema(table.name, source_columns)
    source_select = _source_select_sql(source_table, row_count)
    match_sql = " AND ".join(
        f"target.{_identifier(column)} = source.{_identifier(column)}" for column in key_columns
    )
    return (
        f"DELETE FROM {_table_name(table, schema)} AS target\n"
        f"USING ({source_select}) AS source\n"
        f"WHERE {match_sql}"
    )


def _merge_sql(table: TableSchema, schema: str, row_count: int) -> str:
    if not table.primary_key:
        raise ConfigError("upsert requires a table primary key")
    source_select = _source_select_sql(table, row_count)
    match_sql = " AND ".join(
        f"target.{_identifier(column)} = source.{_identifier(column)}" for column in table.primary_key
    )
    non_key_columns = [column.name for column in table.columns if column.name not in table.primary_key]
    update_sql = ", ".join(
        f"target.{_identifier(column)} = source.{_identifier(column)}" for column in non_key_columns
    )
    insert_columns = ", ".join(_identifier(column.name) for column in table.columns)
    insert_values = ", ".join(f"source.{_identifier(column.name)}" for column in table.columns)
    matched_sql = f"WHEN MATCHED THEN UPDATE SET {update_sql}\n" if update_sql else ""
    return (
        f"MERGE INTO {_table_name(table, schema)} AS target\n"
        f"USING ({source_select}) AS source\n"
        f"ON {match_sql}\n"
        f"{matched_sql}"
        f"WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values})"
    )


def _source_select_sql(table: TableSchema, row_count: int) -> str:
    row_select = "SELECT " + ", ".join(
        f"{_placeholder(table, i)} AS {_identifier(column.name)}" for i, column in enumerate(table.columns)
    )
    return " UNION ALL ".join(row_select for _ in range(row_count))


def _placeholder(table: TableSchema, index: int) -> str:
    if index in table.array_indexes:
        return "PARSE_JSON(%s)"
    return "%s"


def _create_table_sql(table: TableSchema, schema: str) -> str:
    return _create_table_statement_sql("CREATE OR REPLACE TABLE", table, schema)


def _create_table_if_not_exists_sql(table: TableSchema, schema: str) -> str:
    return _create_table_statement_sql("CREATE TABLE IF NOT EXISTS", table, schema)


def _create_table_statement_sql(prefix: str, table: TableSchema, schema: str) -> str:
    definitions = []
    for column in table.columns:
        sql = f"{column.name} {_type_sql(column.kind)}"
        if not column.nullable:
            sql += " NOT NULL"
        definitions.append(sql)
    if table.primary_key:
        definitions.append(f"PRIMARY KEY ({', '.join(table.primary_key)})")
    return (
        f"{prefix} {_table_name(table, schema)} (\n    "
        + ",\n    ".join(definitions)
        + "\n)"
    )


def _table_name(table: TableSchema, schema: str) -> str:
    return f"{schema}.{_identifier(table.base_name)}"


def _identifier(identifier: str) -> str:
    if not IDENTIFIER_RE.fullmatch(identifier):
        raise ConfigError(f"expected a simple Snowflake identifier: {identifier}")
    return identifier


def _type_sql(kind: str) -> str:
    if kind == "array":
        return "VARIANT"
    if kind == "boolean":
        return "BOOLEAN"
    if kind == "text":
        return "TEXT"
    if kind == "varchar":
        return "VARCHAR"
    raise ValueError(f"unsupported column kind: {kind}")


def load_private_key(pem_bytes: bytes, passphrase: str | None) -> bytes:
    from cryptography.hazmat.primitives import serialization

    password = passphrase.encode() if passphrase else None
    private_key = serialization.load_pem_private_key(pem_bytes, password=password)
    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def load_private_key_from_path(path: str, passphrase: str | None) -> bytes:
    return load_private_key(Path(path).read_bytes(), passphrase)
