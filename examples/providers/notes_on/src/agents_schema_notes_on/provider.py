"""Implementation for the notes_on example provider."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import yaml

AGENTS_SCHEMA = "agents"
INSERT_BATCH_SIZE = 1000
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


class NotesOnError(Exception):
    """Raised for user-facing provider configuration and validation errors."""


@dataclass(frozen=True)
class Column:
    name: str
    kind: str
    nullable: bool = True


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[Column, ...]
    primary_key: tuple[str, ...] = ()

    @property
    def variant_indexes(self) -> set[int]:
        return {i for i, column in enumerate(self.columns) if column.kind == "variant"}


ROOT = Table(
    "root",
    (
        Column("provider", "varchar", nullable=False),
        Column("key", "varchar", nullable=False),
        Column("content", "text", nullable=False),
    ),
    primary_key=("provider", "key"),
)

NOTES_ON_SCHEMATA = Table(
    "notes_on_schemata",
    (
        Column("note_id", "varchar", nullable=False),
        Column("schema_name", "varchar", nullable=False),
        Column("kind", "varchar", nullable=False),
        Column("tags", "variant"),
        Column("title", "varchar"),
        Column("content", "text", nullable=False),
        Column("author", "varchar"),
        Column("source", "varchar"),
        Column("confidence", "float"),
        Column("importance", "float"),
        Column("created_at", "timestamp"),
        Column("updated_at", "timestamp"),
    ),
    primary_key=("note_id",),
)

NOTES_ON_TABLES = Table(
    "notes_on_tables",
    (
        Column("note_id", "varchar", nullable=False),
        Column("table_catalog", "varchar"),
        Column("table_schema", "varchar", nullable=False),
        Column("table_name", "varchar", nullable=False),
        Column("kind", "varchar", nullable=False),
        Column("tags", "variant"),
        Column("title", "varchar"),
        Column("content", "text", nullable=False),
        Column("author", "varchar"),
        Column("source", "varchar"),
        Column("confidence", "float"),
        Column("importance", "float"),
        Column("created_at", "timestamp"),
        Column("updated_at", "timestamp"),
    ),
    primary_key=("note_id",),
)

NOTES_ON_COLUMNS = Table(
    "notes_on_columns",
    (
        Column("note_id", "varchar", nullable=False),
        Column("table_catalog", "varchar"),
        Column("table_schema", "varchar", nullable=False),
        Column("table_name", "varchar", nullable=False),
        Column("column_name", "varchar", nullable=False),
        Column("kind", "varchar", nullable=False),
        Column("tags", "variant"),
        Column("title", "varchar"),
        Column("content", "text", nullable=False),
        Column("author", "varchar"),
        Column("source", "varchar"),
        Column("confidence", "float"),
        Column("importance", "float"),
        Column("created_at", "timestamp"),
        Column("updated_at", "timestamp"),
    ),
    primary_key=("note_id",),
)

ROOT_ROWS = (
    (
        "notes_on",
        "overview",
        "# Notes On\nPortable, object-scoped annotations for warehouse schemas, tables, and columns.",
    ),
    ("notes_on", "schemata", "One row per note attached to a warehouse schema. See AGENTS.NOTES_ON_SCHEMATA."),
    ("notes_on", "tables", "One row per note attached to a warehouse table. See AGENTS.NOTES_ON_TABLES."),
    ("notes_on", "columns", "One row per note attached to a warehouse column. See AGENTS.NOTES_ON_COLUMNS."),
)

COMMON_NOTE_FIELDS = (
    "note_id",
    "kind",
    "tags",
    "title",
    "content",
    "author",
    "source",
    "confidence",
    "importance",
    "created_at",
    "updated_at",
)
SCHEMA_NOTE_FIELDS = ("note_id", "schema_name", *COMMON_NOTE_FIELDS[1:])
TABLE_NOTE_FIELDS = ("note_id", "table_catalog", "table_schema", "table_name", *COMMON_NOTE_FIELDS[1:])
COLUMN_NOTE_FIELDS = (
    "note_id",
    "table_catalog",
    "table_schema",
    "table_name",
    "column_name",
    *COMMON_NOTE_FIELDS[1:],
)
TOP_LEVEL_FIELDS = frozenset({"schema_notes", "table_notes", "column_notes"})
NOTE_SECTIONS = (
    ("schema_notes", SCHEMA_NOTE_FIELDS, ("schema_name",)),
    ("table_notes", TABLE_NOTE_FIELDS, ("table_schema", "table_name")),
    ("column_notes", COLUMN_NOTE_FIELDS, ("table_schema", "table_name", "column_name")),
)
NOTE_SCORE_FIELDS = frozenset({"confidence", "importance"})
NOTE_ARRAY_FIELDS = frozenset({"tags"})
NOTE_TIMESTAMP_FIELDS = frozenset({"created_at", "updated_at"})
NOTE_STRING_FIELDS = (
    frozenset(COMMON_NOTE_FIELDS)
    - NOTE_SCORE_FIELDS
    - NOTE_ARRAY_FIELDS
    - NOTE_TIMESTAMP_FIELDS
    | {"schema_name", "table_catalog", "table_schema", "table_name", "column_name"}
)


def run(notes_file: Path) -> None:
    schema_notes, table_notes, column_notes = load_notes_file(notes_file)
    with SnowflakeDestination.from_env() as dest:
        dest.upsert_rows(ROOT, ROOT_ROWS)
        dest.replace_table(NOTES_ON_SCHEMATA)
        dest.replace_table(NOTES_ON_TABLES)
        dest.replace_table(NOTES_ON_COLUMNS)
        if schema_notes:
            dest.insert_rows(NOTES_ON_SCHEMATA, schema_notes)
        if table_notes:
            dest.insert_rows(NOTES_ON_TABLES, table_notes)
        if column_notes:
            dest.insert_rows(NOTES_ON_COLUMNS, column_notes)
    print(
        "  notes_on: "
        f"{len(schema_notes)} schema notes, "
        f"{len(table_notes)} table notes, "
        f"{len(column_notes)} column notes"
    )


def load_notes_file(path: Path) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        raise NotesOnError(f"notes file is not valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise NotesOnError("notes file must be a YAML object")
    _reject_unknown_fields(data, TOP_LEVEL_FIELDS, "notes file")

    rows_by_section: dict[str, list[tuple[Any, ...]]] = {}
    seen_note_ids: set[str] = set()
    for section, fields, required_fields in NOTE_SECTIONS:
        raw_notes = data.get(section, [])
        if not isinstance(raw_notes, list):
            raise NotesOnError(f"{section} must be a list")
        rows_by_section[section] = _load_note_rows(
            raw_notes,
            section,
            fields,
            required_fields,
            seen_note_ids,
        )

    return (
        rows_by_section["schema_notes"],
        rows_by_section["table_notes"],
        rows_by_section["column_notes"],
    )


def _load_note_rows(
    raw_notes: list[Any],
    section: str,
    fields: tuple[str, ...],
    required_fields: tuple[str, ...],
    seen_note_ids: set[str],
) -> list[tuple[Any, ...]]:
    rows = []
    allowed_fields = frozenset(fields)
    for index, raw_note in enumerate(raw_notes):
        path = f"{section}[{index}]"
        if not isinstance(raw_note, dict):
            raise NotesOnError(f"{path} must be an object")
        _reject_unknown_fields(raw_note, allowed_fields, path)
        _validate_strings(raw_note, NOTE_STRING_FIELDS, path)
        _validate_string_lists(raw_note, NOTE_ARRAY_FIELDS, path)
        _validate_timestamps(raw_note, NOTE_TIMESTAMP_FIELDS, path)
        _validate_scores(raw_note, NOTE_SCORE_FIELDS, path)
        note_id = _required_str(raw_note, "note_id", path)
        if note_id in seen_note_ids:
            raise NotesOnError(f"duplicate note_id: {note_id}")
        seen_note_ids.add(note_id)
        _required_str(raw_note, "kind", path)
        _required_str(raw_note, "content", path)
        for field in required_fields:
            _required_str(raw_note, field, path)
        rows.append(tuple(raw_note.get(field) for field in fields))
    return rows


def _required_str(data: dict[str, Any], field: str, path: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise NotesOnError(f"{path}.{field} is required")
    return value


def _reject_unknown_fields(data: dict[str, Any], allowed: frozenset[str], path: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise NotesOnError(f"{path} has unknown field: {unknown[0]}")


def _validate_strings(data: dict[str, Any], fields: frozenset[str], path: str) -> None:
    for field in fields:
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            raise NotesOnError(f"{path}.{field} must be a string")


def _validate_string_lists(data: dict[str, Any], fields: frozenset[str], path: str) -> None:
    for field in fields:
        value = data.get(field)
        if value is None:
            continue
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            raise NotesOnError(f"{path}.{field} must be a list of strings")


def _validate_timestamps(data: dict[str, Any], fields: frozenset[str], path: str) -> None:
    for field in fields:
        value = data.get(field)
        if value is not None and not isinstance(value, (str, date, datetime)):
            raise NotesOnError(f"{path}.{field} must be a timestamp")


def _validate_scores(data: dict[str, Any], fields: frozenset[str], path: str) -> None:
    for field in fields:
        value = data.get(field)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise NotesOnError(f"{path}.{field} must be a number")
        if not 0.0 <= float(value) <= 1.0:
            raise NotesOnError(f"{path}.{field} must be between 0 and 1")


class SnowflakeDestination:
    def __init__(self, config: dict[str, Any]) -> None:
        import snowflake.connector

        self._con = snowflake.connector.connect(**_snowflake_connect_kwargs(config))

    @classmethod
    def from_env(cls) -> "SnowflakeDestination":
        return cls(warehouse_credentials_from_env())

    def __enter__(self) -> "SnowflakeDestination":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        self._con.close()

    def replace_table(self, table: Table) -> None:
        with self._con.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {AGENTS_SCHEMA}")
            cur.execute(_create_table_sql(table))

    def upsert_rows(self, table: Table, rows: Iterable[tuple[Any, ...]]) -> None:
        bind_rows = _bind_rows(table, rows)
        if not bind_rows:
            return
        with self._con.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {AGENTS_SCHEMA}")
            cur.execute(_create_table_if_not_exists_sql(table))
            for batch in _batched(bind_rows, INSERT_BATCH_SIZE):
                cur.execute(_merge_sql(table, len(batch)), _flatten(batch))

    def insert_rows(self, table: Table, rows: Iterable[tuple[Any, ...]]) -> None:
        bind_rows = _bind_rows(table, rows)
        if not bind_rows:
            return
        with self._con.cursor() as cur:
            for batch in _batched(bind_rows, INSERT_BATCH_SIZE):
                cur.execute(_insert_sql(table, len(batch)), _flatten(batch))


def warehouse_credentials_from_env() -> dict[str, Any]:
    raw = os.environ.get("WAREHOUSE_CREDENTIALS")
    if not raw:
        raise NotesOnError("missing required WAREHOUSE_CREDENTIALS secret")
    try:
        destination = json.loads(raw)
    except json.JSONDecodeError:
        try:
            destination = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            raise NotesOnError(f"WAREHOUSE_CREDENTIALS is not valid JSON or YAML: {e}") from e
    if not isinstance(destination, dict):
        raise NotesOnError("WAREHOUSE_CREDENTIALS must be a JSON or YAML object")
    if destination.get("type") != "snowflake":
        raise NotesOnError("WAREHOUSE_CREDENTIALS.type must be snowflake")
    return destination


def _snowflake_connect_kwargs(destination: dict[str, Any]) -> dict[str, Any]:
    required = ["account", "user", "warehouse", "database"]
    missing = [name for name in required if not destination.get(name)]
    has_password = bool(destination.get("password"))
    has_private_key_pem = bool(destination.get("private_key_pem"))
    has_private_key_path = bool(destination.get("private_key_path"))
    if not has_password and not has_private_key_pem and not has_private_key_path:
        missing.append("password, private_key_pem, or private_key_path")
    if missing:
        raise NotesOnError("WAREHOUSE_CREDENTIALS missing keys: " + ", ".join(missing))

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
        kwargs["private_key"] = _load_private_key(destination["private_key_pem"].encode(), passphrase)
    elif has_private_key_path:
        kwargs["private_key"] = _load_private_key(Path(destination["private_key_path"]).read_bytes(), passphrase)
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


def _bind_rows(table: Table, rows: Iterable[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    bind_rows = []
    for row in rows:
        bind_row = []
        for i, value in enumerate(row):
            if i in table.variant_indexes:
                bind_row.append(json.dumps(value or []))
            else:
                bind_row.append(value)
        bind_rows.append(tuple(bind_row))
    return bind_rows


def _batched(rows: list[tuple[Any, ...]], size: int) -> Iterable[list[tuple[Any, ...]]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _insert_sql(table: Table, row_count: int) -> str:
    row_select = "SELECT " + ",".join(_placeholder(table, i) for i in range(len(table.columns)))
    values_sql = " UNION ALL ".join(row_select for _ in range(row_count))
    return f"INSERT INTO {_table_name(table)} {values_sql}"


def _merge_sql(table: Table, row_count: int) -> str:
    if not table.primary_key:
        raise NotesOnError("upsert requires a table primary key")
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
        f"MERGE INTO {_table_name(table)} AS target\n"
        f"USING ({source_select}) AS source\n"
        f"ON {match_sql}\n"
        f"{matched_sql}"
        f"WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values})"
    )


def _source_select_sql(table: Table, row_count: int) -> str:
    row_select = "SELECT " + ", ".join(
        f"{_placeholder(table, i)} AS {_identifier(column.name)}" for i, column in enumerate(table.columns)
    )
    return " UNION ALL ".join(row_select for _ in range(row_count))


def _placeholder(table: Table, index: int) -> str:
    if index in table.variant_indexes:
        return "PARSE_JSON(%s)"
    return "%s"


def _flatten(rows: list[tuple[Any, ...]]) -> tuple[Any, ...]:
    return tuple(value for row in rows for value in row)


def _create_table_sql(table: Table) -> str:
    return _create_table_statement_sql("CREATE OR REPLACE TABLE", table)


def _create_table_if_not_exists_sql(table: Table) -> str:
    return _create_table_statement_sql("CREATE TABLE IF NOT EXISTS", table)


def _create_table_statement_sql(prefix: str, table: Table) -> str:
    definitions = []
    for column in table.columns:
        sql = f"{column.name} {_type_sql(column.kind)}"
        if not column.nullable:
            sql += " NOT NULL"
        definitions.append(sql)
    if table.primary_key:
        definitions.append(f"PRIMARY KEY ({', '.join(table.primary_key)})")
    return f"{prefix} {_table_name(table)} (\n    " + ",\n    ".join(definitions) + "\n)"


def _table_name(table: Table) -> str:
    return f"{AGENTS_SCHEMA}.{_identifier(table.name)}"


def _identifier(identifier: str) -> str:
    if not IDENTIFIER_RE.fullmatch(identifier):
        raise NotesOnError(f"expected a simple Snowflake identifier: {identifier}")
    return identifier


def _type_sql(kind: str) -> str:
    if kind == "float":
        return "FLOAT"
    if kind == "text":
        return "TEXT"
    if kind == "timestamp":
        return "TIMESTAMP"
    if kind == "variant":
        return "VARIANT"
    if kind == "varchar":
        return "VARCHAR"
    raise ValueError(f"unsupported column kind: {kind}")
