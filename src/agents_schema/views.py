"""Information-schema-like context views over provider-normalized views."""
from __future__ import annotations

from .destinations import Destination
from .root import upsert_provider_root

__all__ = [
    "CORE_VIEW_NAMES",
    "PROVIDER_VIEW_NAMES",
    "create_context_views",
    "build_context_view_sql",
]

CORE_VIEW_NAMES = frozenset({"tables", "columns", "relationships", "metrics", "entities"})
PROVIDER_VIEW_NAMES = frozenset(
    {
        "dbt_tables",
        "dbt_columns",
        "dbt_relationships",
        "lookml_tables",
        "lookml_columns",
        "lookml_metrics",
        "osi_tables",
        "osi_columns",
        "osi_relationships",
        "osi_metrics",
    }
)
_LOOKML_RELATION_RE = r"^[A-Za-z_][A-Za-z0-9_$]*([.][A-Za-z_][A-Za-z0-9_$]*){0,2}$"


def create_context_views(dest: Destination) -> None:
    """Create provider-normalized views and generic context views."""
    upsert_provider_root(dest, "core")
    for name, sql in build_context_view_sql(dest.existing_table_names()).items():
        dest.replace_view(name, sql)


def build_context_view_sql(existing_tables: set[str]) -> dict[str, str]:
    existing = {name.lower() for name in existing_tables}
    provider_views = _provider_view_sql(existing)
    return provider_views | {
        "tables": _merge_table_views(provider_views),
        "columns": _union_provider_views(provider_views, "columns", _COLUMN_COLUMNS),
        "relationships": _union_provider_views(provider_views, "relationships", _RELATIONSHIP_COLUMNS),
        "metrics": _union_provider_views(provider_views, "metrics", _METRIC_COLUMNS),
        "entities": _union_provider_views(provider_views, "entities", _ENTITY_COLUMNS),
    }


def _provider_view_sql(existing: set[str]) -> dict[str, str]:
    return {
        "dbt_tables": _dbt_tables_sql(existing),
        "dbt_columns": _dbt_columns_sql(existing),
        "dbt_relationships": _dbt_relationships_sql(existing),
        "lookml_tables": _lookml_tables_sql(existing),
        "lookml_columns": _lookml_columns_sql(existing),
        "lookml_metrics": _lookml_metrics_sql(existing),
        "osi_tables": _osi_tables_sql(existing),
        "osi_columns": _osi_columns_sql(existing),
        "osi_relationships": _osi_relationships_sql(existing),
        "osi_metrics": _osi_metrics_sql(existing),
    }


def _union_provider_views(provider_views: dict[str, str], suffix: str, columns: list[tuple[str, str]]) -> str:
    selects = [
        f"SELECT {', '.join(name for name, _ in columns)}\nFROM agents.{view_name}"
        for view_name in provider_views
        if view_name.endswith(f"_{suffix}")
    ]
    return _union_or_empty(selects, columns)


def _merge_table_views(provider_views: dict[str, str]) -> str:
    table_views = [view_name for view_name in provider_views if view_name.endswith("_tables")]
    provider_selects = [
        _provider_table_select(alias)
        for alias in (_provider_alias(view_name) for view_name in table_views)
    ]
    count_selects = [
        _provider_table_count_select(alias, "memories_count")
        for alias in (_provider_alias(view_name) for view_name in table_views)
    ]
    warning_selects = [
        _provider_table_count_select(alias, "warnings_count")
        for alias in (_provider_alias(view_name) for view_name in table_views)
    ]
    joins = "\n".join(
        _provider_table_join(view_name, _provider_alias(view_name))
        for view_name in table_views
    )
    return f"""SELECT
  t.table_catalog,
  t.table_schema,
  t.table_name,
  t.table_owner,
  t.table_type,
  t.is_transient,
  t.clustering_key,
  t.row_count,
  t.bytes,
  t.retention_time,
  t.self_referencing_column_name,
  t.reference_generation,
  t.user_defined_type_catalog,
  t.user_defined_type_schema,
  t.user_defined_type_name,
  t.is_insertable_into,
  t.is_typed,
  t.commit_action,
  t.created,
  t.last_altered,
  t.last_ddl,
  t.last_ddl_by,
  t.auto_clustering_on,
  t.comment,
  t.is_temporary,
  t.is_iceberg,
  t.is_dynamic,
  t.is_immutable,
  t.is_hybrid,
  {",\n  ".join(provider_selects)},
  {" + ".join(count_selects)} AS memories_count,
  {" + ".join(warning_selects)} AS warnings_count
FROM information_schema.tables t
{joins}"""


def _provider_alias(view_name: str) -> str:
    return view_name.removesuffix("_tables")


def _provider_table_select(alias: str) -> str:
    return f"""{alias}.display_name AS {alias}_display_name,
  {alias}.description AS {alias}_description,
  {alias}.ai_context AS {alias}_ai_context,
  {alias}.source_object_id AS {alias}_source_object_id,
  {alias}.source_path AS {alias}_source_path,
  {alias}.materialization AS {alias}_materialization,
  {alias}.tags AS {alias}_tags"""


def _provider_table_count_select(alias: str, column: str) -> str:
    return f"COALESCE({alias}.{column}, 0)"


def _provider_table_join(view_name: str, alias: str) -> str:
    return f"""LEFT JOIN (
  SELECT
    table_catalog,
    table_schema,
    table_name,
    MIN(display_name) AS display_name,
    MIN(description) AS description,
    MIN(ai_context) AS ai_context,
    LISTAGG(source_object_id, ', ') WITHIN GROUP (ORDER BY source_object_id) AS source_object_id,
    LISTAGG(source_path, ', ') WITHIN GROUP (ORDER BY source_path) AS source_path,
    MIN(materialization) AS materialization,
    ANY_VALUE(tags) AS tags,
    SUM(memories_count) AS memories_count,
    SUM(warnings_count) AS warnings_count
  FROM agents.{view_name}
  WHERE table_schema IS NOT NULL
    AND table_name IS NOT NULL
  GROUP BY table_catalog, table_schema, table_name
) {alias}
  ON ({alias}.table_catalog IS NULL OR LOWER(t.table_catalog) = LOWER({alias}.table_catalog))
 AND LOWER(t.table_schema) = LOWER({alias}.table_schema)
 AND LOWER(t.table_name) = LOWER({alias}.table_name)"""


def _union_or_empty(selects: list[str], columns: list[tuple[str, str]]) -> str:
    if selects:
        return "\nUNION ALL\n".join(selects)
    projection = ",\n  ".join(f"CAST(NULL AS {kind}) AS {name}" for name, kind in columns)
    return f"SELECT\n  {projection}\nWHERE 1 = 0"


def _lookml_relation_identity_sql(sql_table_name: str, fallback_name: str) -> tuple[str, str, str]:
    relation_is_simple = f"REGEXP_LIKE({sql_table_name}, '{_LOOKML_RELATION_RE}')"
    part_count = f"REGEXP_COUNT({sql_table_name}, '[.]')"
    return (
        f"""CASE
    WHEN {relation_is_simple} AND {part_count} = 2
      THEN SPLIT_PART({sql_table_name}, '.', 1)
    ELSE CAST(NULL AS VARCHAR)
  END AS table_catalog""",
        f"""CASE
    WHEN {relation_is_simple} AND {part_count} = 2
      THEN SPLIT_PART({sql_table_name}, '.', 2)
    WHEN {relation_is_simple} AND {part_count} = 1
      THEN SPLIT_PART({sql_table_name}, '.', 1)
    ELSE CAST(NULL AS VARCHAR)
  END AS table_schema""",
        f"""CASE
    WHEN {relation_is_simple} AND {part_count} = 2
      THEN SPLIT_PART({sql_table_name}, '.', 3)
    WHEN {relation_is_simple} AND {part_count} = 1
      THEN SPLIT_PART({sql_table_name}, '.', 2)
    WHEN {relation_is_simple} AND {part_count} = 0
      THEN {sql_table_name}
    ELSE {fallback_name}
  END AS table_name""",
    )


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
    ("memories_count", "NUMBER"),
    ("warnings_count", "NUMBER"),
]

_COLUMN_COLUMNS = [
    ("table_catalog", "VARCHAR"),
    ("table_schema", "VARCHAR"),
    ("table_name", "VARCHAR"),
    ("column_name", "VARCHAR"),
    ("ordinal_position", "NUMBER"),
    ("data_type", "VARCHAR"),
    ("is_nullable", "BOOLEAN"),
    ("display_name", "VARCHAR"),
    ("description", "TEXT"),
    ("ai_context", "TEXT"),
    ("semantic_type", "VARCHAR"),
    ("is_time_dimension", "BOOLEAN"),
    ("expression", "TEXT"),
    ("source_provider", "VARCHAR"),
    ("source_object_id", "VARCHAR"),
    ("memories_count", "NUMBER"),
    ("warnings_count", "NUMBER"),
]

_RELATIONSHIP_COLUMNS = [
    ("relationship_name", "VARCHAR"),
    ("from_catalog", "VARCHAR"),
    ("from_schema", "VARCHAR"),
    ("from_table", "VARCHAR"),
    ("from_column", "VARCHAR"),
    ("to_catalog", "VARCHAR"),
    ("to_schema", "VARCHAR"),
    ("to_table", "VARCHAR"),
    ("to_column", "VARCHAR"),
    ("relationship_type", "VARCHAR"),
    ("multiplicity", "VARCHAR"),
    ("source_provider", "VARCHAR"),
    ("source_object_id", "VARCHAR"),
    ("memories_count", "NUMBER"),
    ("warnings_count", "NUMBER"),
]

_METRIC_COLUMNS = [
    ("metric_name", "VARCHAR"),
    ("display_name", "VARCHAR"),
    ("description", "TEXT"),
    ("ai_context", "TEXT"),
    ("expression", "TEXT"),
    ("source_provider", "VARCHAR"),
    ("source_object_id", "VARCHAR"),
    ("dataset_name", "VARCHAR"),
    ("view_name", "VARCHAR"),
    ("memories_count", "NUMBER"),
    ("warnings_count", "NUMBER"),
]

_ENTITY_COLUMNS = [
    ("entity_id", "VARCHAR"),
    ("display_name", "VARCHAR"),
    ("description", "TEXT"),
    ("source_provider", "VARCHAR"),
    ("source_object_id", "VARCHAR"),
    ("primary_table_schema", "VARCHAR"),
    ("primary_table_name", "VARCHAR"),
    ("primary_key_columns", "VARIANT"),
    ("memories_count", "NUMBER"),
    ("warnings_count", "NUMBER"),
]


def _dbt_tables_sql(existing: set[str]) -> str:
    if "dbt_model" not in existing:
        return _union_or_empty([], _TABLE_COLUMNS)
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
  tags,
  0 AS memories_count,
  0 AS warnings_count
FROM agents.dbt_model"""


def _dbt_columns_sql(existing: set[str]) -> str:
    if not {"dbt_model", "dbt_column"}.issubset(existing):
        return _union_or_empty([], _COLUMN_COLUMNS)
    return """SELECT
  CAST(NULL AS VARCHAR) AS table_catalog,
  m.schema_name AS table_schema,
  m.name AS table_name,
  c.column_name,
  CAST(NULL AS NUMBER) AS ordinal_position,
  c.data_type,
  CAST(NULL AS BOOLEAN) AS is_nullable,
  c.column_name AS display_name,
  c.description,
  CAST(NULL AS TEXT) AS ai_context,
  CAST(NULL AS VARCHAR) AS semantic_type,
  CAST(NULL AS BOOLEAN) AS is_time_dimension,
  CAST(NULL AS TEXT) AS expression,
  'dbt' AS source_provider,
  c.model_id || '.' || c.column_name AS source_object_id,
  0 AS memories_count,
  0 AS warnings_count
FROM agents.dbt_column c
JOIN agents.dbt_model m ON m.unique_id = c.model_id"""


def _dbt_relationships_sql(existing: set[str]) -> str:
    if not {"dbt_dependency", "dbt_model"}.issubset(existing):
        return _union_or_empty([], _RELATIONSHIP_COLUMNS)
    return """SELECT
  d.upstream_id || ' -> ' || d.downstream_id AS relationship_name,
  CAST(NULL AS VARCHAR) AS from_catalog,
  upstream.schema_name AS from_schema,
  upstream.name AS from_table,
  CAST(NULL AS VARCHAR) AS from_column,
  CAST(NULL AS VARCHAR) AS to_catalog,
  downstream.schema_name AS to_schema,
  downstream.name AS to_table,
  CAST(NULL AS VARCHAR) AS to_column,
  'lineage' AS relationship_type,
  CAST(NULL AS VARCHAR) AS multiplicity,
  'dbt' AS source_provider,
  d.upstream_id || ' -> ' || d.downstream_id AS source_object_id,
  0 AS memories_count,
  0 AS warnings_count
FROM agents.dbt_dependency d
JOIN agents.dbt_model upstream ON upstream.unique_id = d.upstream_id
JOIN agents.dbt_model downstream ON downstream.unique_id = d.downstream_id"""


def _lookml_tables_sql(existing: set[str]) -> str:
    if "lookml_view" not in existing:
        return _union_or_empty([], _TABLE_COLUMNS)
    catalog_sql, schema_sql, table_sql = _lookml_relation_identity_sql("sql_table_name", "name")
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
  PARSE_JSON('[]') AS tags,
  0 AS memories_count,
  0 AS warnings_count
FROM agents.lookml_view"""


def _lookml_columns_sql(existing: set[str]) -> str:
    if not {"lookml_dimension", "lookml_view"}.issubset(existing):
        return _union_or_empty([], _COLUMN_COLUMNS)
    catalog_sql, schema_sql, table_sql = _lookml_relation_identity_sql("v.sql_table_name", "v.name")
    return f"""SELECT
  {catalog_sql},
  {schema_sql},
  {table_sql},
  d.field_name AS column_name,
  CAST(NULL AS NUMBER) AS ordinal_position,
  d.type AS data_type,
  CAST(NULL AS BOOLEAN) AS is_nullable,
  d.field_name AS display_name,
  d.description,
  d.ai_context,
  d.field_kind AS semantic_type,
  d.field_kind = 'dimension_group' AS is_time_dimension,
  d.sql AS expression,
  'lookml' AS source_provider,
  d.view_name || '.' || d.field_name AS source_object_id,
  0 AS memories_count,
  0 AS warnings_count
FROM agents.lookml_dimension d
JOIN agents.lookml_view v ON v.name = d.view_name"""


def _lookml_metrics_sql(existing: set[str]) -> str:
    if "lookml_measure" not in existing:
        return _union_or_empty([], _METRIC_COLUMNS)
    return """SELECT
  measure_name AS metric_name,
  measure_name AS display_name,
  description,
  ai_context,
  COALESCE(sql, filters) AS expression,
  'lookml' AS source_provider,
  view_name || '.' || measure_name AS source_object_id,
  CAST(NULL AS VARCHAR) AS dataset_name,
  view_name,
  0 AS memories_count,
  0 AS warnings_count
FROM agents.lookml_measure"""


def _osi_tables_sql(existing: set[str]) -> str:
    if "osi_dataset" not in existing:
        return _union_or_empty([], _TABLE_COLUMNS)
    catalog_sql, schema_sql, table_sql = _lookml_relation_identity_sql("source_table", "name")
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
  PARSE_JSON('[]') AS tags,
  0 AS memories_count,
  0 AS warnings_count
FROM agents.osi_dataset"""


def _osi_columns_sql(existing: set[str]) -> str:
    if not {"osi_dataset", "osi_field"}.issubset(existing):
        return _union_or_empty([], _COLUMN_COLUMNS)
    return """SELECT
  CAST(NULL AS VARCHAR) AS table_catalog,
  CAST(NULL AS VARCHAR) AS table_schema,
  d.source_table AS table_name,
  f.field_name AS column_name,
  CAST(NULL AS NUMBER) AS ordinal_position,
  CAST(NULL AS VARCHAR) AS data_type,
  CAST(NULL AS BOOLEAN) AS is_nullable,
  COALESCE(f.label, f.field_name) AS display_name,
  f.description,
  f.ai_context,
  CAST(NULL AS VARCHAR) AS semantic_type,
  f.is_time_dimension,
  f.expression,
  'osi' AS source_provider,
  f.dataset_name || '.' || f.field_name AS source_object_id,
  0 AS memories_count,
  0 AS warnings_count
FROM agents.osi_field f
JOIN agents.osi_dataset d ON d.name = f.dataset_name"""


def _osi_relationships_sql(existing: set[str]) -> str:
    if not {"osi_dataset", "osi_relationship"}.issubset(existing):
        return _union_or_empty([], _RELATIONSHIP_COLUMNS)
    return """SELECT
  r.name AS relationship_name,
  CAST(NULL AS VARCHAR) AS from_catalog,
  CAST(NULL AS VARCHAR) AS from_schema,
  from_dataset.source_table AS from_table,
  r.from_columns::TEXT AS from_column,
  CAST(NULL AS VARCHAR) AS to_catalog,
  CAST(NULL AS VARCHAR) AS to_schema,
  to_dataset.source_table AS to_table,
  r.to_columns::TEXT AS to_column,
  'semantic_relationship' AS relationship_type,
  CAST(NULL AS VARCHAR) AS multiplicity,
  'osi' AS source_provider,
  r.name AS source_object_id,
  0 AS memories_count,
  0 AS warnings_count
FROM agents.osi_relationship r
JOIN agents.osi_dataset from_dataset ON from_dataset.name = r.from_dataset
JOIN agents.osi_dataset to_dataset ON to_dataset.name = r.to_dataset"""


def _osi_metrics_sql(existing: set[str]) -> str:
    if "osi_metric" not in existing:
        return _union_or_empty([], _METRIC_COLUMNS)
    return """SELECT
  name AS metric_name,
  name AS display_name,
  description,
  ai_context,
  expression,
  'osi' AS source_provider,
  name AS source_object_id,
  CAST(NULL AS VARCHAR) AS dataset_name,
  CAST(NULL AS VARCHAR) AS view_name,
  0 AS memories_count,
  0 AS warnings_count
FROM agents.osi_metric"""
