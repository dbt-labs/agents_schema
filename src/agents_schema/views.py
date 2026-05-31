"""Information-schema-like context views over provider-normalized views.

v1 scope: extend the surfaces ``INFORMATION_SCHEMA`` already has — `TABLES` and
`COLUMNS` — rather than inventing new object types. Each metadata provider
publishes a normalized ``AGENTS.<PROVIDER>_TABLES`` / ``AGENTS.<PROVIDER>_COLUMNS``
view with a shared shape. ``AGENTS.TABLES`` and ``AGENTS.COLUMNS`` then take the
native ``INFORMATION_SCHEMA`` view as the row spine (``SELECT t.*``) and merge
**every** provider view that exists by object identity, appending each
provider's columns under a ``<provider>_`` prefix.

The merge is generic: no native column list is hardcoded (``SELECT t.*`` inherits
whatever the account exposes), and no provider is special-cased. A provider that
ships a new ``*_TABLES`` view later — e.g. a memory provider contributing
``memories_count`` — is picked up automatically with no change here.

Relationships and metrics are intentionally out of scope for v1. The
information-schema-faithful home for relationships is the
``REFERENTIAL_CONSTRAINTS`` / ``KEY_COLUMN_USAGE`` family; see the proposal.
"""
from __future__ import annotations

import sys

from .destinations import Destination
from .root import upsert_provider_root

__all__ = [
    "CORE_VIEW_NAMES",
    "PROVIDER_VIEW_NAMES",
    "create_context_views",
    "build_context_view_sql",
]

CORE_VIEW_NAMES = frozenset({"tables", "columns"})
PROVIDER_VIEW_NAMES = frozenset(
    {
        "dbt_tables",
        "dbt_columns",
        "lookml_tables",
        "lookml_columns",
        "osi_tables",
        "osi_columns",
    }
)
_RELATION_RE = r"^[A-Za-z_][A-Za-z0-9_$]*([.][A-Za-z_][A-Za-z0-9_$]*){0,2}$"


def create_context_views(dest: Destination) -> None:
    """Create provider-normalized views and the generic context views.

    Fail-soft: a view that cannot be created warns but never breaks the
    surrounding ingestion, which has already written the provider tables.
    """
    upsert_provider_root(dest, "core")
    for name, sql in build_context_view_sql(dest.existing_table_names()).items():
        try:
            dest.replace_view(name, sql)
        except Exception as e:  # noqa: BLE001 - the view layer must not fail ingestion
            print(f"  warning: could not create view agents.{name}: {e}", file=sys.stderr)


def build_context_view_sql(existing_tables: set[str]) -> dict[str, str]:
    existing = {name.lower() for name in existing_tables}
    provider_views = _provider_view_sql(existing)
    return provider_views | {
        "tables": _merge_view(provider_views, "tables", "information_schema.tables", _TABLE_IDENTITY, _TABLE_MERGE),
        "columns": _merge_view(provider_views, "columns", "information_schema.columns", _COLUMN_IDENTITY, _COLUMN_MERGE),
    }


def _provider_view_sql(existing: set[str]) -> dict[str, str]:
    return {
        "dbt_tables": _dbt_tables_sql(existing),
        "dbt_columns": _dbt_columns_sql(existing),
        "lookml_tables": _lookml_tables_sql(existing),
        "lookml_columns": _lookml_columns_sql(existing),
        "osi_tables": _osi_tables_sql(existing),
        "osi_columns": _osi_columns_sql(existing),
    }


# --- generic merge over the native information_schema spine ------------------


def _merge_view(
    provider_views: dict[str, str],
    suffix: str,
    spine: str,
    identity: tuple[str, ...],
    merge_columns: tuple[str, ...],
) -> str:
    views = [name for name in provider_views if name.endswith(f"_{suffix}")]
    selects = [
        ",\n  ".join(f"{alias}.{column} AS {alias}_{column}" for column in merge_columns)
        for alias in (_provider_alias(name, suffix) for name in views)
    ]
    joins = "\n".join(_merge_join(name, _provider_alias(name, suffix), identity, merge_columns) for name in views)
    # Every enrichment column is `<provider>_` prefixed, so `t.*` (the native
    # spine columns) can never collide with appended columns. Keep that prefix
    # if more enrichment is added later.
    enrichment = (",\n  " + ",\n  ".join(selects)) if selects else ""
    return f"SELECT\n  t.*{enrichment}\nFROM {spine} t\n{joins}"


def _provider_alias(view_name: str, suffix: str) -> str:
    return view_name.removesuffix(f"_{suffix}")


def _merge_join(view_name: str, alias: str, identity: tuple[str, ...], merge_columns: tuple[str, ...]) -> str:
    id_select = ",\n    ".join(identity)
    agg_select = ",\n    ".join(f"{_agg(column)} AS {column}" for column in merge_columns)
    group_by = ", ".join(identity)
    required = [column for column in identity if column not in ("table_catalog", "table_schema")]
    where = " AND ".join(f"{column} IS NOT NULL" for column in required)
    on = "\n AND ".join(_merge_on(alias, column) for column in identity)
    return (
        f"LEFT JOIN (\n"
        f"  SELECT\n    {id_select},\n    {agg_select}\n"
        f"  FROM agents.{view_name}\n"
        f"  WHERE {where}\n"
        f"  GROUP BY {group_by}\n"
        f") {alias}\n  ON {on}"
    )


def _merge_on(alias: str, column: str) -> str:
    # Enrichment attaches by case-folded object name, not a guaranteed-unique
    # key. A provider row with NULL table_catalog matches the spine in any
    # catalog; since the spine is single-database, that is effectively
    # schema+name (plus column) identity.
    if column == "table_catalog":
        return f"({alias}.{column} IS NULL OR LOWER(t.{column}) = LOWER({alias}.{column}))"
    return f"LOWER(t.{column}) = LOWER({alias}.{column})"


def _agg(column: str) -> str:
    if column == "tags":
        return f"ANY_VALUE({column})"
    if column in ("source_object_id", "source_path"):
        return f"LISTAGG({column}, ', ') WITHIN GROUP (ORDER BY {column})"
    return f"MIN({column})"


def _empty_view(columns: list[tuple[str, str]]) -> str:
    projection = ",\n  ".join(f"CAST(NULL AS {kind}) AS {name}" for name, kind in columns)
    return f"SELECT\n  {projection}\nWHERE 1 = 0"


def _relation_identity_sql(relation: str, fallback_name: str) -> tuple[str, str, str]:
    """Split a 1-, 2-, or 3-part relation reference into catalog/schema/table."""
    is_simple = f"REGEXP_LIKE({relation}, '{_RELATION_RE}')"
    part_count = f"REGEXP_COUNT({relation}, '[.]')"
    return (
        f"""CASE
    WHEN {is_simple} AND {part_count} = 2
      THEN SPLIT_PART({relation}, '.', 1)
    ELSE CAST(NULL AS VARCHAR)
  END AS table_catalog""",
        f"""CASE
    WHEN {is_simple} AND {part_count} = 2
      THEN SPLIT_PART({relation}, '.', 2)
    WHEN {is_simple} AND {part_count} = 1
      THEN SPLIT_PART({relation}, '.', 1)
    ELSE CAST(NULL AS VARCHAR)
  END AS table_schema""",
        f"""CASE
    WHEN {is_simple} AND {part_count} = 2
      THEN SPLIT_PART({relation}, '.', 3)
    WHEN {is_simple} AND {part_count} = 1
      THEN SPLIT_PART({relation}, '.', 2)
    WHEN {is_simple} AND {part_count} = 0
      THEN {relation}
    ELSE {fallback_name}
  END AS table_name""",
    )


# --- provider-normalized view shapes -----------------------------------------

_TABLE_COLUMNS = [
    ("table_catalog", "VARCHAR"),
    ("table_schema", "VARCHAR"),
    ("table_name", "VARCHAR"),
    ("table_type", "VARCHAR"),
    ("display_name", "VARCHAR"),
    ("description", "TEXT"),
    ("ai_context", "TEXT"),
    ("source_provider", "VARCHAR"),
    ("source_object_id", "VARCHAR"),
    ("source_path", "VARCHAR"),
    ("materialization", "VARCHAR"),
    ("tags", "VARIANT"),
]
_TABLE_IDENTITY = ("table_catalog", "table_schema", "table_name")
_TABLE_MERGE = tuple(
    name for name, _ in _TABLE_COLUMNS if name not in _TABLE_IDENTITY and name != "source_provider"
)

_COLUMN_COLUMNS = [
    ("table_catalog", "VARCHAR"),
    ("table_schema", "VARCHAR"),
    ("table_name", "VARCHAR"),
    ("column_name", "VARCHAR"),
    ("display_name", "VARCHAR"),
    ("description", "TEXT"),
    ("ai_context", "TEXT"),
    ("semantic_type", "VARCHAR"),
    ("is_time_dimension", "BOOLEAN"),
    ("expression", "TEXT"),
    ("source_provider", "VARCHAR"),
    ("source_object_id", "VARCHAR"),
]
_COLUMN_IDENTITY = ("table_catalog", "table_schema", "table_name", "column_name")
_COLUMN_MERGE = tuple(
    name for name, _ in _COLUMN_COLUMNS if name not in _COLUMN_IDENTITY and name != "source_provider"
)


def _dbt_tables_sql(existing: set[str]) -> str:
    if "dbt_model" not in existing:
        return _empty_view(_TABLE_COLUMNS)
    return """SELECT
  CAST(NULL AS VARCHAR) AS table_catalog,
  schema_name AS table_schema,
  name AS table_name,
  'DBT_MODEL' AS table_type,
  name AS display_name,
  description,
  CAST(NULL AS TEXT) AS ai_context,
  'dbt' AS source_provider,
  unique_id AS source_object_id,
  file_path AS source_path,
  materialization,
  tags
FROM agents.dbt_model"""


def _dbt_columns_sql(existing: set[str]) -> str:
    if not {"dbt_model", "dbt_column"}.issubset(existing):
        return _empty_view(_COLUMN_COLUMNS)
    return """SELECT
  CAST(NULL AS VARCHAR) AS table_catalog,
  m.schema_name AS table_schema,
  m.name AS table_name,
  c.column_name,
  c.column_name AS display_name,
  c.description,
  CAST(NULL AS TEXT) AS ai_context,
  CAST(NULL AS VARCHAR) AS semantic_type,
  CAST(NULL AS BOOLEAN) AS is_time_dimension,
  CAST(NULL AS TEXT) AS expression,
  'dbt' AS source_provider,
  c.model_id || '.' || c.column_name AS source_object_id
FROM agents.dbt_column c
JOIN agents.dbt_model m ON m.unique_id = c.model_id"""


def _lookml_tables_sql(existing: set[str]) -> str:
    if "lookml_view" not in existing:
        return _empty_view(_TABLE_COLUMNS)
    catalog_sql, schema_sql, table_sql = _relation_identity_sql("sql_table_name", "name")
    return f"""SELECT
  {catalog_sql},
  {schema_sql},
  {table_sql},
  'LOOKML_VIEW' AS table_type,
  COALESCE(label, name) AS display_name,
  description,
  ai_context,
  'lookml' AS source_provider,
  name AS source_object_id,
  file_path AS source_path,
  CAST(NULL AS VARCHAR) AS materialization,
  PARSE_JSON('[]') AS tags
FROM agents.lookml_view"""


def _lookml_columns_sql(existing: set[str]) -> str:
    if not {"lookml_dimension", "lookml_view"}.issubset(existing):
        return _empty_view(_COLUMN_COLUMNS)
    catalog_sql, schema_sql, table_sql = _relation_identity_sql("v.sql_table_name", "v.name")
    return f"""SELECT
  {catalog_sql},
  {schema_sql},
  {table_sql},
  d.field_name AS column_name,
  d.field_name AS display_name,
  d.description,
  d.ai_context,
  d.field_kind AS semantic_type,
  d.field_kind = 'dimension_group' AND COALESCE(d.type, 'time') = 'time' AS is_time_dimension,
  d.sql AS expression,
  'lookml' AS source_provider,
  d.view_name || '.' || d.field_name AS source_object_id
FROM agents.lookml_dimension d
JOIN agents.lookml_view v ON v.name = d.view_name"""


def _osi_tables_sql(existing: set[str]) -> str:
    if "osi_dataset" not in existing:
        return _empty_view(_TABLE_COLUMNS)
    catalog_sql, schema_sql, table_sql = _relation_identity_sql("source_table", "name")
    return f"""SELECT
  {catalog_sql},
  {schema_sql},
  {table_sql},
  'OSI_DATASET' AS table_type,
  name AS display_name,
  description,
  ai_context,
  'osi' AS source_provider,
  name AS source_object_id,
  CAST(NULL AS VARCHAR) AS source_path,
  CAST(NULL AS VARCHAR) AS materialization,
  PARSE_JSON('[]') AS tags
FROM agents.osi_dataset"""


def _osi_columns_sql(existing: set[str]) -> str:
    if not {"osi_dataset", "osi_field"}.issubset(existing):
        return _empty_view(_COLUMN_COLUMNS)
    catalog_sql, schema_sql, table_sql = _relation_identity_sql("d.source_table", "d.name")
    return f"""SELECT
  {catalog_sql},
  {schema_sql},
  {table_sql},
  f.field_name AS column_name,
  COALESCE(f.label, f.field_name) AS display_name,
  f.description,
  f.ai_context,
  CAST(NULL AS VARCHAR) AS semantic_type,
  f.is_time_dimension,
  f.expression,
  'osi' AS source_provider,
  f.dataset_name || '.' || f.field_name AS source_object_id
FROM agents.osi_field f
JOIN agents.osi_dataset d ON d.name = f.dataset_name"""
