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
class Dialect:
    """Warehouse-specific SQL details that differ between destinations."""

    name: str
    type_map: dict[str, str]
    array_placeholder: str
    emit_primary_key: bool
    delete_via_merge: bool


SNOWFLAKE = Dialect(
    name="snowflake",
    type_map={"array": "VARIANT", "boolean": "BOOLEAN", "text": "TEXT", "varchar": "VARCHAR"},
    array_placeholder="PARSE_JSON(%s)",
    emit_primary_key=True,
    delete_via_merge=False,
)

# Delta: arrays are JSON text in STRING, PRIMARY KEY is informational-only (omitted),
# and DELETE has no USING clause so deletes run as MERGE ... WHEN MATCHED THEN DELETE.
DATABRICKS = Dialect(
    name="databricks",
    type_map={"array": "STRING", "boolean": "BOOLEAN", "text": "STRING", "varchar": "STRING"},
    array_placeholder="%s",
    emit_primary_key=False,
    delete_via_merge=True,
)


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
    def upsert_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None: ...
    def insert_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None: ...
    def delete_rows(self, table: TableSchema, key_columns: tuple[str, ...], rows: Iterable[tuple[Any, ...]]) -> None: ...
    def close(self) -> None: ...
    def __enter__(self) -> "Destination": ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...


class _SqlDestination:
    """Shared MERGE/INSERT/DELETE logic over a DB-API connection and a Dialect."""

    def __init__(self, con: Any, dialect: Dialect) -> None:
        self._con = con
        self._dialect = dialect
        self._agents_schema = AGENTS_SCHEMA

    def __enter__(self) -> "_SqlDestination":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        self._con.close()

    def replace_table(self, table: TableSchema) -> None:
        with self._con.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {self._agents_schema}")
            cur.execute(_create_table_sql(table, self._agents_schema, self._dialect))

    def upsert_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None:
        bind_rows = _bind_rows(table, rows)
        if not bind_rows:
            return
        with self._con.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {self._agents_schema}")
            cur.execute(_create_table_if_not_exists_sql(table, self._agents_schema, self._dialect))
            for batch in _batched(bind_rows, INSERT_BATCH_SIZE):
                cur.execute(
                    _merge_sql(table, self._agents_schema, len(batch), self._dialect),
                    _flatten(batch),
                )

    def insert_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None:
        bind_rows = _bind_rows(table, rows)
        if not bind_rows:
            return
        with self._con.cursor() as cur:
            for batch in _batched(bind_rows, INSERT_BATCH_SIZE):
                cur.execute(
                    _insert_sql(table, self._agents_schema, len(batch), self._dialect),
                    _flatten(batch),
                )

    def delete_rows(self, table: TableSchema, key_columns: tuple[str, ...], rows: Iterable[tuple[Any, ...]]) -> None:
        bind_rows = list(rows)
        if not bind_rows:
            return
        with self._con.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {self._agents_schema}")
            cur.execute(_create_table_if_not_exists_sql(table, self._agents_schema, self._dialect))
            for batch in _batched(bind_rows, INSERT_BATCH_SIZE):
                cur.execute(
                    _delete_sql(table, self._agents_schema, key_columns, len(batch), self._dialect),
                    _flatten(batch),
                )


class SnowflakeDestination(_SqlDestination):
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        connect_kwargs: dict[str, Any] | None = None,
    ) -> None:
        import snowflake.connector

        if connect_kwargs is None:
            if config is None:
                raise ConfigError("SnowflakeDestination requires config or connect_kwargs")
            connect_kwargs = _snowflake_connect_kwargs(config)
        super().__init__(snowflake.connector.connect(**connect_kwargs), SNOWFLAKE)


class DatabricksDestination(_SqlDestination):
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        connect_kwargs: dict[str, Any] | None = None,
    ) -> None:
        from databricks import sql as databricks_sql

        if connect_kwargs is None:
            if config is None:
                raise ConfigError("DatabricksDestination requires config or connect_kwargs")
            connect_kwargs = _databricks_connect_kwargs(config)
        super().__init__(databricks_sql.connect(**connect_kwargs), DATABRICKS)


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


def _insert_sql(table: TableSchema, schema: str, row_count: int, dialect: Dialect = SNOWFLAKE) -> str:
    row_select = "SELECT " + ",".join(_placeholder(table, i, dialect) for i in range(len(table.columns)))
    values_sql = " UNION ALL ".join(row_select for _ in range(row_count))
    return f"INSERT INTO {_table_name(table, schema)} {values_sql}"


def _delete_sql(
    table: TableSchema,
    schema: str,
    key_columns: tuple[str, ...],
    row_count: int,
    dialect: Dialect = SNOWFLAKE,
) -> str:
    if not key_columns:
        raise ConfigError("delete requires at least one key column")
    source_columns = tuple(Column(name, "varchar", nullable=False) for name in key_columns)
    source_table = TableSchema(table.name, source_columns)
    source_select = _source_select_sql(source_table, row_count, dialect)
    match_sql = " AND ".join(
        f"target.{_identifier(column)} = source.{_identifier(column)}" for column in key_columns
    )
    if dialect.delete_via_merge:
        return (
            f"MERGE INTO {_table_name(table, schema)} AS target\n"
            f"USING ({source_select}) AS source\n"
            f"ON {match_sql}\n"
            f"WHEN MATCHED THEN DELETE"
        )
    return (
        f"DELETE FROM {_table_name(table, schema)} AS target\n"
        f"USING ({source_select}) AS source\n"
        f"WHERE {match_sql}"
    )


def _merge_sql(table: TableSchema, schema: str, row_count: int, dialect: Dialect = SNOWFLAKE) -> str:
    if not table.primary_key:
        raise ConfigError("upsert requires a table primary key")
    source_select = _source_select_sql(table, row_count, dialect)
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


def _source_select_sql(table: TableSchema, row_count: int, dialect: Dialect = SNOWFLAKE) -> str:
    row_select = "SELECT " + ", ".join(
        f"{_placeholder(table, i, dialect)} AS {_identifier(column.name)}"
        for i, column in enumerate(table.columns)
    )
    return " UNION ALL ".join(row_select for _ in range(row_count))


def _placeholder(table: TableSchema, index: int, dialect: Dialect = SNOWFLAKE) -> str:
    if index in table.array_indexes:
        return dialect.array_placeholder
    return "%s"


def _flatten(rows: list[tuple[Any, ...]]) -> tuple[Any, ...]:
    return tuple(value for row in rows for value in row)


def open_destination(cfg: dict[str, Any]) -> Destination:
    dest_type = warehouse_type(cfg)
    if dest_type == "snowflake":
        return SnowflakeDestination(cfg)
    if dest_type == "databricks":
        return DatabricksDestination(cfg)
    raise ConfigError(f"unsupported destination type: {dest_type}")


def _snowflake_connect_kwargs(cfg: dict[str, Any]) -> dict[str, Any]:
    destination = warehouse_credentials_from_env()
    if destination.get("type") != "snowflake":
        raise ConfigError("WAREHOUSE_CREDENTIALS.type must be snowflake")
    return _snowflake_connect_kwargs_from_secret(destination)


def _databricks_connect_kwargs(cfg: dict[str, Any]) -> dict[str, Any]:
    destination = warehouse_credentials_from_env()
    if destination.get("type") != "databricks":
        raise ConfigError("WAREHOUSE_CREDENTIALS.type must be databricks")
    return _databricks_connect_kwargs_from_secret(destination)


def _databricks_connect_kwargs_from_secret(destination: dict[str, Any]) -> dict[str, Any]:
    required = ["server_hostname", "http_path"]
    missing = [name for name in required if not destination.get(name)]
    if not destination.get("access_token"):
        missing.append("access_token")
    if missing:
        raise ConfigError("WAREHOUSE_CREDENTIALS missing keys: " + ", ".join(missing))

    kwargs: dict[str, Any] = {
        "server_hostname": destination["server_hostname"],
        "http_path": destination["http_path"],
        "access_token": destination["access_token"],
    }
    if catalog := destination.get("catalog"):
        kwargs["catalog"] = catalog
    return kwargs


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


def _create_table_sql(table: TableSchema, schema: str, dialect: Dialect = SNOWFLAKE) -> str:
    return _create_table_statement_sql("CREATE OR REPLACE TABLE", table, schema, dialect)


def _create_table_if_not_exists_sql(table: TableSchema, schema: str, dialect: Dialect = SNOWFLAKE) -> str:
    return _create_table_statement_sql("CREATE TABLE IF NOT EXISTS", table, schema, dialect)


def _create_table_statement_sql(
    prefix: str, table: TableSchema, schema: str, dialect: Dialect = SNOWFLAKE
) -> str:
    definitions = []
    for column in table.columns:
        sql = f"{column.name} {_type_sql(column.kind, dialect)}"
        if not column.nullable:
            sql += " NOT NULL"
        definitions.append(sql)
    if dialect.emit_primary_key and table.primary_key:
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
        raise ConfigError(f"expected a simple unquoted identifier: {identifier}")
    return identifier


def _type_sql(kind: str, dialect: Dialect = SNOWFLAKE) -> str:
    try:
        return dialect.type_map[kind]
    except KeyError:
        raise ValueError(f"unsupported column kind: {kind}")
