"""Warehouse destinations for agents-schema writes."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

import yaml

from .config import ConfigError, warehouse_type

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

    def insert_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None:
        rows = list(rows)
        if not rows:
            return
        bind_rows = []
        for row in rows:
            bind_row = []
            for i, value in enumerate(row):
                if i in table.array_indexes:
                    bind_row.append(json.dumps(value or []))
                else:
                    bind_row.append(value)
            bind_rows.append(tuple(bind_row))
        with self._con.cursor() as cur:
            for batch in _batched(bind_rows, INSERT_BATCH_SIZE):
                cur.execute(_insert_sql(table, self._agents_schema, len(batch)), _flatten(batch))


def _batched(rows: list[tuple[Any, ...]], size: int) -> Iterable[list[tuple[Any, ...]]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _insert_sql(table: TableSchema, schema: str, row_count: int) -> str:
    row_select = "SELECT " + ",".join(_placeholder(table, i) for i in range(len(table.columns)))
    values_sql = " UNION ALL ".join(row_select for _ in range(row_count))
    return f"INSERT INTO {_table_name(table, schema)} {values_sql}"


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
    raw = os.environ.get("WAREHOUSE_CREDENTIALS")
    if not raw:
        raise ConfigError("missing required WAREHOUSE_CREDENTIALS secret")
    return _snowflake_connect_kwargs_from_secret(raw)


def _snowflake_connect_kwargs_from_secret(raw: str) -> dict[str, Any]:
    try:
        destination = json.loads(raw)
    except json.JSONDecodeError:
        try:
            destination = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            raise ConfigError(f"WAREHOUSE_CREDENTIALS is not valid JSON or YAML: {e}") from e
    if not isinstance(destination, dict):
        raise ConfigError("WAREHOUSE_CREDENTIALS must be a JSON or YAML object")
    if destination.get("type") != "snowflake":
        raise ConfigError("WAREHOUSE_CREDENTIALS.type must be snowflake")

    required = ["account", "user", "warehouse", "database"]
    missing = [name for name in required if not destination.get(name)]
    has_password = bool(destination.get("password"))
    has_private_key = bool(destination.get("private_key_path"))
    if not has_password and not has_private_key:
        missing.append("password or private_key_path")
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
    if has_private_key:
        kwargs["private_key"] = _load_private_key(
            Path(destination["private_key_path"]),
            destination.get("private_key_passphrase"),
        )
    else:
        kwargs["password"] = destination["password"]
    return kwargs


def _load_private_key(path: Path, passphrase: str | None) -> bytes:
    from cryptography.hazmat.primitives import serialization

    password = passphrase.encode() if passphrase else None
    private_key = serialization.load_pem_private_key(path.read_bytes(), password=password)
    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _create_table_sql(table: TableSchema, schema: str) -> str:
    definitions = []
    for column in table.columns:
        sql = f"{column.name} {_type_sql(column.kind)}"
        if not column.nullable:
            sql += " NOT NULL"
        definitions.append(sql)
    if table.primary_key:
        definitions.append(f"PRIMARY KEY ({', '.join(table.primary_key)})")
    return (
        f"CREATE OR REPLACE TABLE {_table_name(table, schema)} (\n    "
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
