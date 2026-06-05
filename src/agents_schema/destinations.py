"""Warehouse destinations for agents-schema writes."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

import yaml

from .config import ConfigError, SUPPORTED_WAREHOUSE_TYPES, warehouse_type

INSERT_BATCH_SIZE = 1000
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
AGENTS_SCHEMA = "agents"


@dataclass(frozen=True)
class Column:
    name: str
    kind: str
    nullable: bool = True


@dataclass(frozen=True)
class TableSchema:
    name: str
    columns: tuple[Column, ...]
    primary_key: tuple[str, ...] = ()

    @property
    def array_indexes(self) -> set[int]:
        return {i for i, column in enumerate(self.columns) if column.kind == "array"}


class Destination(Protocol):
    def replace_table(self, table: TableSchema) -> None: ...
    def replace_view(self, name: str, sql: str) -> None: ...
    def existing_relation_names(self) -> set[str]: ...
    def upsert_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None: ...
    def insert_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None: ...
    def close(self) -> None: ...
    def __enter__(self) -> "Destination": ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...


class SnowflakeDestination:
    def __init__(self, config: dict[str, Any]) -> None:
        import snowflake.connector

        self._agents_schema = AGENTS_SCHEMA
        self._con = snowflake.connector.connect(**_snowflake_connect_kwargs(config))

    def __enter__(self) -> "SnowflakeDestination":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        self._con.close()

    def replace_table(self, table: TableSchema) -> None:
        with self._con.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {self._agents_schema}")
            cur.execute(_create_table_sql(table, self._agents_schema))

    def replace_view(self, name: str, sql: str) -> None:
        with self._con.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {self._agents_schema}")
            cur.execute(_create_view_sql(name, sql, self._agents_schema))

    def existing_relation_names(self) -> set[str]:
        with self._con.cursor() as cur:
            cur.execute(
                "SELECT LOWER(table_name) "
                "FROM information_schema.tables "
                "WHERE table_schema = UPPER(%s)",
                (self._agents_schema,),
            )
            return {str(row[0]) for row in cur.fetchall()}

    def upsert_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None:
        bind_rows = _bind_rows(table, rows)
        if not bind_rows:
            return
        with self._con.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {self._agents_schema}")
            cur.execute(_create_table_if_not_exists_sql(table, self._agents_schema))
            for batch in _batched(bind_rows, INSERT_BATCH_SIZE):
                cur.execute(_merge_sql(table, self._agents_schema, len(batch)), _flatten(batch))

    def insert_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None:
        bind_rows = _bind_rows(table, rows)
        if not bind_rows:
            return
        with self._con.cursor() as cur:
            for batch in _batched(bind_rows, INSERT_BATCH_SIZE):
                cur.execute(_insert_sql(table, self._agents_schema, len(batch)), _flatten(batch))


def _bind_rows(table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    bind_rows = []
    for row in rows:
        bind_row = []
        for i, value in enumerate(row):
            if i in table.array_indexes:
                bind_row.append(json.dumps(value or []))
            else:
                bind_row.append(value)
        bind_rows.append(tuple(bind_row))
    return bind_rows


def _batched(rows: list[tuple[Any, ...]], size: int) -> Iterable[list[tuple[Any, ...]]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _insert_sql(table: TableSchema, schema: str, row_count: int) -> str:
    row_select = "SELECT " + ",".join(_placeholder(table, i) for i in range(len(table.columns)))
    values_sql = " UNION ALL ".join(row_select for _ in range(row_count))
    return f"INSERT INTO {_table_name(table, schema)} {values_sql}"


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


def _flatten(rows: list[tuple[Any, ...]]) -> tuple[Any, ...]:
    return tuple(value for row in rows for value in row)


def open_destination(cfg: dict[str, Any]) -> Destination:
    dest_type = warehouse_type(cfg)
    if dest_type == "snowflake":
        return SnowflakeDestination(cfg)
    raise ConfigError(f"unsupported destination type: {dest_type}")


def _snowflake_connect_kwargs(cfg: dict[str, Any]) -> dict[str, Any]:
    destination = warehouse_credentials_from_env()
    if destination.get("type") != "snowflake":
        raise ConfigError("WAREHOUSE_CREDENTIALS.type must be snowflake")
    return _snowflake_connect_kwargs_from_secret(destination)


def warehouse_credentials_from_env() -> dict[str, Any]:
    raw = os.environ.get("WAREHOUSE_CREDENTIALS")
    if not raw:
        raise ConfigError("missing required WAREHOUSE_CREDENTIALS secret")
    destination = _parse_warehouse_credentials(raw)
    destination_type = destination.get("type")
    if not isinstance(destination_type, str) or not destination_type:
        raise ConfigError("WAREHOUSE_CREDENTIALS.type is required")
    if destination_type not in SUPPORTED_WAREHOUSE_TYPES:
        supported = ", ".join(sorted(SUPPORTED_WAREHOUSE_TYPES))
        raise ConfigError(
            f"unsupported WAREHOUSE_CREDENTIALS.type {destination_type!r}; supported types: {supported}"
        )
    return destination


def warehouse_type_from_env() -> str:
    return str(warehouse_credentials_from_env()["type"])


def _parse_warehouse_credentials(raw: str) -> dict[str, Any]:
    try:
        destination = json.loads(raw)
    except json.JSONDecodeError:
        try:
            destination = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            raise ConfigError(f"WAREHOUSE_CREDENTIALS is not valid JSON or YAML: {e}") from e
    if not isinstance(destination, dict):
        raise ConfigError("WAREHOUSE_CREDENTIALS must be a JSON or YAML object")
    return destination


def _snowflake_connect_kwargs_from_secret(destination: dict[str, Any]) -> dict[str, Any]:
    required = ["account", "user", "warehouse", "database"]
    missing = [name for name in required if not destination.get(name)]
    has_password = bool(destination.get("password"))
    has_private_key_pem = bool(destination.get("private_key_pem"))
    has_private_key_path = bool(destination.get("private_key_path"))
    if not has_password and not has_private_key_pem and not has_private_key_path:
        missing.append("password, private_key_pem, or private_key_path")
    if missing:
        raise ConfigError("WAREHOUSE_CREDENTIALS missing keys: " + ", ".join(missing))

    kwargs: dict[str, Any] = {
        "account": destination["account"],
        "user": destination["user"],
        "warehouse": destination["warehouse"],
        "database": destination["database"],
    }
    if role := destination.get("role"):
        kwargs["role"] = role
    passphrase = destination.get("private_key_passphrase")
    if has_private_key_pem:
        kwargs["private_key"] = _load_private_key(
            destination["private_key_pem"].encode(),
            passphrase,
        )
    elif has_private_key_path:
        kwargs["private_key"] = _load_private_key(
            Path(destination["private_key_path"]).read_bytes(),
            passphrase,
        )
    else:
        kwargs["password"] = destination["password"]
    return kwargs


def _load_private_key(pem_bytes: bytes, passphrase: str | None) -> bytes:
    from cryptography.hazmat.primitives import serialization

    password = passphrase.encode() if passphrase else None
    private_key = serialization.load_pem_private_key(pem_bytes, password=password)
    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _create_table_sql(table: TableSchema, schema: str) -> str:
    return _create_table_statement_sql("CREATE OR REPLACE TABLE", table, schema)


def _create_table_if_not_exists_sql(table: TableSchema, schema: str) -> str:
    return _create_table_statement_sql("CREATE TABLE IF NOT EXISTS", table, schema)


def _create_view_sql(name: str, sql: str, schema: str) -> str:
    return f"CREATE OR REPLACE VIEW {schema}.{_identifier(name)} AS\n{sql}"


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
    name = table.name.split(".")[-1]
    return f"{schema}.{_identifier(name)}"


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
