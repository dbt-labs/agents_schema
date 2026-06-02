"""Metadata export connectors for BI, semantic-layer, and catalog systems."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .destinations import Column, Destination, TableSchema, open_destination
from .metadata_io import load_metadata_documents
from .root import upsert_provider_root

__all__ = ["SUPPORTED_PROVIDERS", "run"]


@dataclass(frozen=True)
class Provider:
    name: str
    tables: tuple[TableSchema, ...]
    parse: Callable[[list[Any]], dict[TableSchema, list[tuple[Any, ...]]]]
    summary: Callable[[dict[TableSchema, list[tuple[Any, ...]]]], str]


POWERBI_WORKSPACE = TableSchema(
    "agents.powerbi_workspace",
    (
        Column("workspace_id", "varchar", nullable=False),
        Column("name", "varchar"),
        Column("description", "text"),
        Column("state", "varchar"),
    ),
    primary_key=("workspace_id",),
)
POWERBI_SEMANTIC_MODEL = TableSchema(
    "agents.powerbi_semantic_model",
    (
        Column("model_id", "varchar", nullable=False),
        Column("workspace_id", "varchar"),
        Column("name", "varchar"),
        Column("description", "text"),
        Column("configured_by", "varchar"),
        Column("endorsement", "varchar"),
    ),
    primary_key=("model_id",),
)
POWERBI_TABLE = TableSchema(
    "agents.powerbi_table",
    (
        Column("model_id", "varchar", nullable=False),
        Column("table_name", "varchar", nullable=False),
        Column("description", "text"),
        Column("is_hidden", "boolean"),
    ),
    primary_key=("model_id", "table_name"),
)
POWERBI_COLUMN = TableSchema(
    "agents.powerbi_column",
    (
        Column("model_id", "varchar", nullable=False),
        Column("table_name", "varchar", nullable=False),
        Column("column_name", "varchar", nullable=False),
        Column("data_type", "varchar"),
        Column("description", "text"),
        Column("is_hidden", "boolean"),
    ),
    primary_key=("model_id", "table_name", "column_name"),
)
POWERBI_MEASURE = TableSchema(
    "agents.powerbi_measure",
    (
        Column("model_id", "varchar", nullable=False),
        Column("table_name", "varchar", nullable=False),
        Column("measure_name", "varchar", nullable=False),
        Column("expression", "text"),
        Column("description", "text"),
        Column("is_hidden", "boolean"),
    ),
    primary_key=("model_id", "table_name", "measure_name"),
)
POWERBI_REPORT = TableSchema(
    "agents.powerbi_report",
    (
        Column("report_id", "varchar", nullable=False),
        Column("workspace_id", "varchar"),
        Column("model_id", "varchar"),
        Column("name", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("report_id",),
)
POWERBI_LINEAGE = TableSchema(
    "agents.powerbi_lineage",
    (
        Column("upstream_id", "varchar", nullable=False),
        Column("downstream_id", "varchar", nullable=False),
        Column("relationship_type", "varchar"),
    ),
    primary_key=("upstream_id", "downstream_id"),
)

TABLEAU_WORKBOOK = TableSchema(
    "agents.tableau_workbook",
    (
        Column("workbook_id", "varchar", nullable=False),
        Column("name", "varchar"),
        Column("project_name", "varchar"),
        Column("owner_name", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("workbook_id",),
)
TABLEAU_DATASOURCE = TableSchema(
    "agents.tableau_datasource",
    (
        Column("datasource_id", "varchar", nullable=False),
        Column("name", "varchar"),
        Column("project_name", "varchar"),
        Column("owner_name", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("datasource_id",),
)
TABLEAU_FIELD = TableSchema(
    "agents.tableau_field",
    (
        Column("parent_id", "varchar", nullable=False),
        Column("field_id", "varchar", nullable=False),
        Column("field_name", "varchar"),
        Column("data_type", "varchar"),
        Column("description", "text"),
        Column("is_hidden", "boolean"),
    ),
    primary_key=("parent_id", "field_id"),
)
TABLEAU_DASHBOARD = TableSchema(
    "agents.tableau_dashboard",
    (
        Column("dashboard_id", "varchar", nullable=False),
        Column("workbook_id", "varchar"),
        Column("name", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("dashboard_id",),
)
TABLEAU_LINEAGE = TableSchema(
    "agents.tableau_lineage",
    (
        Column("upstream_id", "varchar", nullable=False),
        Column("downstream_id", "varchar", nullable=False),
        Column("relationship_type", "varchar"),
    ),
    primary_key=("upstream_id", "downstream_id"),
)

DBT_SEMANTIC_MODEL = TableSchema(
    "agents.dbt_semantic_model",
    (
        Column("name", "varchar", nullable=False),
        Column("model_name", "varchar"),
        Column("description", "text"),
        Column("defaults", "array"),
    ),
    primary_key=("name",),
)
DBT_SEMANTIC_ENTITY = TableSchema(
    "agents.dbt_semantic_entity",
    (
        Column("semantic_model_name", "varchar", nullable=False),
        Column("entity_name", "varchar", nullable=False),
        Column("entity_type", "varchar"),
        Column("expr", "text"),
    ),
    primary_key=("semantic_model_name", "entity_name"),
)
DBT_SEMANTIC_DIMENSION = TableSchema(
    "agents.dbt_semantic_dimension",
    (
        Column("semantic_model_name", "varchar", nullable=False),
        Column("dimension_name", "varchar", nullable=False),
        Column("dimension_type", "varchar"),
        Column("expr", "text"),
        Column("description", "text"),
    ),
    primary_key=("semantic_model_name", "dimension_name"),
)
DBT_SEMANTIC_MEASURE = TableSchema(
    "agents.dbt_semantic_measure",
    (
        Column("semantic_model_name", "varchar", nullable=False),
        Column("measure_name", "varchar", nullable=False),
        Column("agg", "varchar"),
        Column("expr", "text"),
        Column("description", "text"),
    ),
    primary_key=("semantic_model_name", "measure_name"),
)
DBT_SEMANTIC_METRIC = TableSchema(
    "agents.dbt_semantic_metric",
    (
        Column("metric_name", "varchar", nullable=False),
        Column("metric_type", "varchar"),
        Column("label", "varchar"),
        Column("description", "text"),
        Column("type_params", "array"),
    ),
    primary_key=("metric_name",),
)

DATAHUB_ENTITY = TableSchema(
    "agents.datahub_entity",
    (
        Column("urn", "varchar", nullable=False),
        Column("entity_type", "varchar"),
        Column("platform", "varchar"),
        Column("name", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("urn",),
)
DATAHUB_FIELD = TableSchema(
    "agents.datahub_field",
    (
        Column("entity_urn", "varchar", nullable=False),
        Column("field_path", "varchar", nullable=False),
        Column("native_data_type", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("entity_urn", "field_path"),
)
DATAHUB_OWNER = TableSchema(
    "agents.datahub_owner",
    (
        Column("entity_urn", "varchar", nullable=False),
        Column("owner_urn", "varchar", nullable=False),
        Column("ownership_type", "varchar"),
    ),
    primary_key=("entity_urn", "owner_urn"),
)
DATAHUB_LINEAGE = TableSchema(
    "agents.datahub_lineage",
    (
        Column("upstream_urn", "varchar", nullable=False),
        Column("downstream_urn", "varchar", nullable=False),
        Column("relationship_type", "varchar"),
    ),
    primary_key=("upstream_urn", "downstream_urn"),
)

OPENMETADATA_ENTITY = TableSchema(
    "agents.openmetadata_entity",
    (
        Column("fully_qualified_name", "varchar", nullable=False),
        Column("entity_type", "varchar"),
        Column("name", "varchar"),
        Column("description", "text"),
        Column("owner_name", "varchar"),
    ),
    primary_key=("fully_qualified_name",),
)
OPENMETADATA_FIELD = TableSchema(
    "agents.openmetadata_field",
    (
        Column("entity_fqn", "varchar", nullable=False),
        Column("field_name", "varchar", nullable=False),
        Column("data_type", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("entity_fqn", "field_name"),
)
OPENMETADATA_LINEAGE = TableSchema(
    "agents.openmetadata_lineage",
    (
        Column("upstream_fqn", "varchar", nullable=False),
        Column("downstream_fqn", "varchar", nullable=False),
        Column("relationship_type", "varchar"),
    ),
    primary_key=("upstream_fqn", "downstream_fqn"),
)

ATLAN_ASSET = TableSchema(
    "agents.atlan_asset",
    (
        Column("guid", "varchar", nullable=False),
        Column("qualified_name", "varchar"),
        Column("asset_type", "varchar"),
        Column("name", "varchar"),
        Column("description", "text"),
        Column("owner_users", "array"),
    ),
    primary_key=("guid",),
)
ATLAN_FIELD = TableSchema(
    "agents.atlan_field",
    (
        Column("asset_guid", "varchar", nullable=False),
        Column("field_guid", "varchar", nullable=False),
        Column("qualified_name", "varchar"),
        Column("name", "varchar"),
        Column("data_type", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("asset_guid", "field_guid"),
)
ATLAN_LINEAGE = TableSchema(
    "agents.atlan_lineage",
    (
        Column("upstream_guid", "varchar", nullable=False),
        Column("downstream_guid", "varchar", nullable=False),
        Column("relationship_type", "varchar"),
    ),
    primary_key=("upstream_guid", "downstream_guid"),
)

ALATION_DATA_SOURCE = TableSchema(
    "agents.alation_data_source",
    (
        Column("data_source_id", "varchar", nullable=False),
        Column("title", "varchar"),
        Column("description", "text"),
        Column("dbtype", "varchar"),
    ),
    primary_key=("data_source_id",),
)
ALATION_TABLE = TableSchema(
    "agents.alation_table",
    (
        Column("table_id", "varchar", nullable=False),
        Column("data_source_id", "varchar"),
        Column("schema_name", "varchar"),
        Column("name", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("table_id",),
)
ALATION_COLUMN = TableSchema(
    "agents.alation_column",
    (
        Column("column_id", "varchar", nullable=False),
        Column("table_id", "varchar"),
        Column("name", "varchar"),
        Column("data_type", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("column_id",),
)
ALATION_GLOSSARY_TERM = TableSchema(
    "agents.alation_glossary_term",
    (
        Column("term_id", "varchar", nullable=False),
        Column("title", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("term_id",),
)

COLLIBRA_ASSET = TableSchema(
    "agents.collibra_asset",
    (
        Column("asset_id", "varchar", nullable=False),
        Column("name", "varchar"),
        Column("display_name", "varchar"),
        Column("asset_type", "varchar"),
        Column("domain_id", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("asset_id",),
)
COLLIBRA_ATTRIBUTE = TableSchema(
    "agents.collibra_attribute",
    (
        Column("asset_id", "varchar", nullable=False),
        Column("attribute_type", "varchar", nullable=False),
        Column("value", "text"),
    ),
    primary_key=("asset_id", "attribute_type"),
)
COLLIBRA_RELATION = TableSchema(
    "agents.collibra_relation",
    (
        Column("source_asset_id", "varchar", nullable=False),
        Column("target_asset_id", "varchar", nullable=False),
        Column("relation_type", "varchar"),
    ),
    primary_key=("source_asset_id", "target_asset_id"),
)
COLLIBRA_RESPONSIBILITY = TableSchema(
    "agents.collibra_responsibility",
    (
        Column("asset_id", "varchar", nullable=False),
        Column("owner_id", "varchar", nullable=False),
        Column("role", "varchar"),
    ),
    primary_key=("asset_id", "owner_id"),
)

METABASE_DATABASE = TableSchema(
    "agents.metabase_database",
    (
        Column("database_id", "varchar", nullable=False),
        Column("name", "varchar"),
        Column("engine", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("database_id",),
)
METABASE_TABLE = TableSchema(
    "agents.metabase_table",
    (
        Column("table_id", "varchar", nullable=False),
        Column("database_id", "varchar"),
        Column("schema_name", "varchar"),
        Column("name", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("table_id",),
)
METABASE_FIELD = TableSchema(
    "agents.metabase_field",
    (
        Column("field_id", "varchar", nullable=False),
        Column("table_id", "varchar"),
        Column("name", "varchar"),
        Column("base_type", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("field_id",),
)
METABASE_CARD = TableSchema(
    "agents.metabase_card",
    (
        Column("card_id", "varchar", nullable=False),
        Column("database_id", "varchar"),
        Column("name", "varchar"),
        Column("description", "text"),
        Column("dataset_query", "array"),
    ),
    primary_key=("card_id",),
)
METABASE_DASHBOARD = TableSchema(
    "agents.metabase_dashboard",
    (
        Column("dashboard_id", "varchar", nullable=False),
        Column("name", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("dashboard_id",),
)

CUBE_CUBE = TableSchema(
    "agents.cube_cube",
    (
        Column("name", "varchar", nullable=False),
        Column("title", "varchar"),
        Column("description", "text"),
        Column("sql", "text"),
        Column("public", "boolean"),
    ),
    primary_key=("name",),
)
CUBE_MEASURE = TableSchema(
    "agents.cube_measure",
    (
        Column("cube_name", "varchar", nullable=False),
        Column("measure_name", "varchar", nullable=False),
        Column("type", "varchar"),
        Column("sql", "text"),
        Column("description", "text"),
    ),
    primary_key=("cube_name", "measure_name"),
)
CUBE_DIMENSION = TableSchema(
    "agents.cube_dimension",
    (
        Column("cube_name", "varchar", nullable=False),
        Column("dimension_name", "varchar", nullable=False),
        Column("type", "varchar"),
        Column("sql", "text"),
        Column("description", "text"),
        Column("primary_key", "boolean"),
    ),
    primary_key=("cube_name", "dimension_name"),
)
CUBE_SEGMENT = TableSchema(
    "agents.cube_segment",
    (
        Column("cube_name", "varchar", nullable=False),
        Column("segment_name", "varchar", nullable=False),
        Column("sql", "text"),
        Column("description", "text"),
    ),
    primary_key=("cube_name", "segment_name"),
)
CUBE_JOIN = TableSchema(
    "agents.cube_join",
    (
        Column("cube_name", "varchar", nullable=False),
        Column("join_name", "varchar", nullable=False),
        Column("relationship", "varchar"),
        Column("sql", "text"),
    ),
    primary_key=("cube_name", "join_name"),
)


def run(provider_name: str, cfg: dict[str, Any]) -> None:
    provider = SUPPORTED_PROVIDERS[provider_name]
    metadata_path = Path(cfg["metadata_connection"]["path"])
    documents = load_metadata_documents(metadata_path)
    rows_by_table = provider.parse(documents)

    with open_destination(cfg) as dest:
        upsert_provider_root(dest, provider.name)
        _create_tables(dest, provider.tables)
        _ingest_rows(dest, rows_by_table)

    print(provider.summary(rows_by_table))


def _create_tables(dest: Destination, tables: Iterable[TableSchema]) -> None:
    for table in tables:
        dest.replace_table(table)


def _ingest_rows(dest: Destination, rows_by_table: dict[TableSchema, list[tuple[Any, ...]]]) -> None:
    for table, rows in rows_by_table.items():
        if rows:
            dest.insert_rows(table, rows)


def _rows(tables: Iterable[TableSchema]) -> dict[TableSchema, list[tuple[Any, ...]]]:
    return {table: [] for table in tables}


def _summarize(provider: str, labels: tuple[tuple[TableSchema, str], ...]) -> Callable[[dict[TableSchema, list[tuple[Any, ...]]]], str]:
    def summary(rows_by_table: dict[TableSchema, list[tuple[Any, ...]]]) -> str:
        parts = [f"{len(rows_by_table.get(table, []))} {label}" for table, label in labels]
        return f"  {provider:<9}" + ", ".join(parts)

    return summary


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in _as_list(value) if isinstance(item, dict)]


def _pick(obj: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        value = obj.get(name)
        if value not in (None, ""):
            return value
    return default


def _nested(obj: dict[str, Any], *path: str) -> Any:
    value: Any = obj
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("description", "plainText", "value", "text", "name"):
            if key in value:
                return _text(value[key])
        return str(value)
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item is not None)
    return str(value)


def _identifier(obj: dict[str, Any], *names: str) -> str | None:
    value = _pick(obj, *names)
    if value is None and "id" in obj:
        value = obj["id"]
    return _text(value)


def _name(obj: dict[str, Any]) -> str | None:
    return _text(_pick(obj, "name", "displayName", "display_name", "title", "label"))


def _description(obj: dict[str, Any]) -> str | None:
    return _text(_pick(obj, "description", "businessDescription", "userDescription", "comment"))


def _bool(obj: dict[str, Any], *names: str) -> bool:
    value = _pick(obj, *names, default=False)
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes"}


def _records(documents: list[Any], *keys: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for document in documents:
        found.extend(_find_records(document, keys))
    return found


def _find_records(value: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []

    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
        if isinstance(candidate, dict):
            nested = _find_records(candidate, keys)
            if nested:
                return nested

    if isinstance(value.get("data"), dict):
        nested = _find_records(value["data"], keys)
        if nested:
            return nested
    if isinstance(value.get("results"), list):
        return [item for item in value["results"] if isinstance(item, dict)]
    if isinstance(value.get("entities"), list):
        return [item for item in value["entities"] if isinstance(item, dict)]
    return [value]


def _owner_name(obj: dict[str, Any]) -> str | None:
    owner = obj.get("owner")
    if isinstance(owner, dict):
        return _name(owner) or _text(_pick(owner, "id", "urn"))
    return _text(owner)


def _platform(obj: dict[str, Any]) -> str | None:
    platform = obj.get("platform")
    if isinstance(platform, dict):
        return _text(_pick(platform, "name", "urn"))
    return _text(platform or obj.get("platformName"))


def _powerbi_parse(documents: list[Any]) -> dict[TableSchema, list[tuple[Any, ...]]]:
    tables = (
        POWERBI_WORKSPACE,
        POWERBI_SEMANTIC_MODEL,
        POWERBI_TABLE,
        POWERBI_COLUMN,
        POWERBI_MEASURE,
        POWERBI_REPORT,
        POWERBI_LINEAGE,
    )
    rows = _rows(tables)
    for workspace in _records(documents, "workspaces"):
        workspace_id = _identifier(workspace, "id", "workspaceId")
        if not workspace_id:
            continue
        rows[POWERBI_WORKSPACE].append((
            workspace_id,
            _name(workspace),
            _description(workspace),
            _text(_pick(workspace, "state", "type")),
        ))

        models = _dicts(_pick(workspace, "datasets", "semanticModels", "models", default=[]))
        for model in models:
            model_id = _identifier(model, "id", "datasetId", "semanticModelId")
            if not model_id:
                continue
            rows[POWERBI_SEMANTIC_MODEL].append((
                model_id,
                workspace_id,
                _name(model),
                _description(model),
                _text(_pick(model, "configuredBy", "configured_by")),
                _text(_pick(model, "endorsement", "endorsementDetails")),
            ))
            for table in _dicts(model.get("tables")):
                table_name = _name(table)
                if not table_name:
                    continue
                rows[POWERBI_TABLE].append((
                    model_id,
                    table_name,
                    _description(table),
                    _bool(table, "isHidden", "hidden"),
                ))
                for column in _dicts(table.get("columns")):
                    column_name = _name(column)
                    if column_name:
                        rows[POWERBI_COLUMN].append((
                            model_id,
                            table_name,
                            column_name,
                            _text(_pick(column, "dataType", "type")),
                            _description(column),
                            _bool(column, "isHidden", "hidden"),
                        ))
                for measure in _dicts(table.get("measures")):
                    measure_name = _name(measure)
                    if measure_name:
                        rows[POWERBI_MEASURE].append((
                            model_id,
                            table_name,
                            measure_name,
                            _text(_pick(measure, "expression", "dax")),
                            _description(measure),
                            _bool(measure, "isHidden", "hidden"),
                        ))

        for report in _dicts(workspace.get("reports")):
            report_id = _identifier(report, "id", "reportId")
            if not report_id:
                continue
            model_id = _text(_pick(report, "datasetId", "semanticModelId"))
            rows[POWERBI_REPORT].append((
                report_id,
                workspace_id,
                model_id,
                _name(report),
                _description(report),
            ))
            if model_id:
                rows[POWERBI_LINEAGE].append((model_id, report_id, "report_uses_model"))

        for relation in _dicts(_pick(workspace, "lineage", "relations", default=[])):
            upstream = _text(_pick(relation, "upstreamId", "sourceId", "from"))
            downstream = _text(_pick(relation, "downstreamId", "targetId", "to"))
            if upstream and downstream:
                rows[POWERBI_LINEAGE].append((upstream, downstream, _text(_pick(relation, "type", "relationshipType"))))
    return rows


def _tableau_parse(documents: list[Any]) -> dict[TableSchema, list[tuple[Any, ...]]]:
    tables = (TABLEAU_WORKBOOK, TABLEAU_DATASOURCE, TABLEAU_FIELD, TABLEAU_DASHBOARD, TABLEAU_LINEAGE)
    rows = _rows(tables)
    for workbook in _records(documents, "workbooks"):
        workbook_id = _identifier(workbook, "id", "luid")
        if not workbook_id:
            continue
        rows[TABLEAU_WORKBOOK].append((
            workbook_id,
            _name(workbook),
            _name(workbook.get("project", {}) if isinstance(workbook.get("project"), dict) else {}),
            _owner_name(workbook),
            _description(workbook),
        ))
        for dashboard in _dicts(_pick(workbook, "dashboards", "sheets", default=[])):
            dashboard_id = _identifier(dashboard, "id", "luid") or f"{workbook_id}.{_name(dashboard)}"
            if dashboard_id:
                rows[TABLEAU_DASHBOARD].append((dashboard_id, workbook_id, _name(dashboard), _description(dashboard)))
        for datasource in _dicts(workbook.get("upstreamDatasources")):
            datasource_id = _identifier(datasource, "id", "luid")
            if datasource_id:
                rows[TABLEAU_LINEAGE].append((datasource_id, workbook_id, "workbook_datasource"))

    for datasource in _records(documents, "datasources", "publishedDatasources", "embeddedDatasources"):
        datasource_id = _identifier(datasource, "id", "luid")
        if not datasource_id:
            continue
        rows[TABLEAU_DATASOURCE].append((
            datasource_id,
            _name(datasource),
            _name(datasource.get("project", {}) if isinstance(datasource.get("project"), dict) else {}),
            _owner_name(datasource),
            _description(datasource),
        ))
        for field in _dicts(_pick(datasource, "fields", "columns", default=[])):
            field_id = _identifier(field, "id", "luid") or _name(field)
            if field_id:
                rows[TABLEAU_FIELD].append((
                    datasource_id,
                    field_id,
                    _name(field),
                    _text(_pick(field, "dataType", "type")),
                    _description(field),
                    _bool(field, "isHidden", "hidden"),
                ))
    return rows


def _dbt_semantic_parse(documents: list[Any]) -> dict[TableSchema, list[tuple[Any, ...]]]:
    tables = (
        DBT_SEMANTIC_MODEL,
        DBT_SEMANTIC_ENTITY,
        DBT_SEMANTIC_DIMENSION,
        DBT_SEMANTIC_MEASURE,
        DBT_SEMANTIC_METRIC,
    )
    rows = _rows(tables)
    for model in _records(documents, "semantic_models", "semanticModels"):
        name = _name(model)
        if not name:
            continue
        rows[DBT_SEMANTIC_MODEL].append((
            name,
            _text(_pick(model, "model", "model_name", "node_relation")),
            _description(model),
            _pick(model, "defaults", default={}),
        ))
        for entity in _dicts(model.get("entities")):
            entity_name = _name(entity)
            if entity_name:
                rows[DBT_SEMANTIC_ENTITY].append((
                    name,
                    entity_name,
                    _text(_pick(entity, "type", "entity_type")),
                    _text(_pick(entity, "expr", "expression")),
                ))
        for dimension in _dicts(model.get("dimensions")):
            dimension_name = _name(dimension)
            if dimension_name:
                rows[DBT_SEMANTIC_DIMENSION].append((
                    name,
                    dimension_name,
                    _text(_pick(dimension, "type", "dimension_type")),
                    _text(_pick(dimension, "expr", "expression")),
                    _description(dimension),
                ))
        for measure in _dicts(model.get("measures")):
            measure_name = _name(measure)
            if measure_name:
                rows[DBT_SEMANTIC_MEASURE].append((
                    name,
                    measure_name,
                    _text(_pick(measure, "agg", "agg_type")),
                    _text(_pick(measure, "expr", "expression")),
                    _description(measure),
                ))

    for metric in _records(documents, "metrics"):
        metric_name = _name(metric)
        if metric_name:
            rows[DBT_SEMANTIC_METRIC].append((
                metric_name,
                _text(_pick(metric, "type", "metric_type")),
                _text(metric.get("label")),
                _description(metric),
                _pick(metric, "type_params", "typeParams", default={}),
            ))
    return rows


def _datahub_parse(documents: list[Any]) -> dict[TableSchema, list[tuple[Any, ...]]]:
    tables = (DATAHUB_ENTITY, DATAHUB_FIELD, DATAHUB_OWNER, DATAHUB_LINEAGE)
    rows = _rows(tables)
    for raw_entity in _records(documents, "entities", "searchResults"):
        entity = raw_entity.get("entity") if isinstance(raw_entity.get("entity"), dict) else raw_entity
        urn = _text(_pick(entity, "urn"))
        if not urn:
            continue
        schema = _pick(entity, "schemaMetadata", default={})
        props = _pick(entity, "properties", "editableProperties", default={})
        rows[DATAHUB_ENTITY].append((
            urn,
            _text(_pick(entity, "type", "entityType")),
            _platform(entity),
            _name(props) or _name(entity),
            _description(props) or _description(entity),
        ))
        if isinstance(schema, dict):
            for field in _dicts(schema.get("fields")):
                field_path = _text(_pick(field, "fieldPath", "name"))
                if field_path:
                    rows[DATAHUB_FIELD].append((
                        urn,
                        field_path,
                        _text(_pick(field, "nativeDataType", "type")),
                        _description(field),
                    ))
        ownership = _pick(entity, "ownership", default={})
        for owner in _dicts(ownership.get("owners") if isinstance(ownership, dict) else []):
            owner_urn = _text(_pick(owner, "ownerUrn", "owner"))
            if owner_urn:
                rows[DATAHUB_OWNER].append((urn, owner_urn, _text(_pick(owner, "type", "ownershipType"))))
        lineage = _pick(entity, "upstreamLineage", "lineage", default={})
        upstreams = lineage.get("upstreams") if isinstance(lineage, dict) else []
        for upstream in _dicts(upstreams):
            upstream_urn = _text(_pick(upstream, "dataset", "urn", "upstreamUrn"))
            if upstream_urn:
                rows[DATAHUB_LINEAGE].append((upstream_urn, urn, _text(_pick(upstream, "type", "relationshipType"))))
    return rows


def _openmetadata_parse(documents: list[Any]) -> dict[TableSchema, list[tuple[Any, ...]]]:
    tables = (OPENMETADATA_ENTITY, OPENMETADATA_FIELD, OPENMETADATA_LINEAGE)
    rows = _rows(tables)
    for entity in _records(documents, "data", "entities"):
        fqn = _text(_pick(entity, "fullyQualifiedName", "fqn", "id"))
        if not fqn:
            continue
        rows[OPENMETADATA_ENTITY].append((
            fqn,
            _text(_pick(entity, "entityType", "type")),
            _name(entity),
            _description(entity),
            _owner_name(entity),
        ))
        for column in _dicts(_pick(entity, "columns", "fields", default=[])):
            column_name = _name(column)
            if column_name:
                rows[OPENMETADATA_FIELD].append((
                    fqn,
                    column_name,
                    _text(_pick(column, "dataType", "type")),
                    _description(column),
                ))
        lineage = _pick(entity, "lineage", default={})
        for upstream in _dicts(_pick(lineage, "upstreamEdges", "upstream", default=[]) if isinstance(lineage, dict) else []):
            upstream_fqn = _text(_pick(upstream, "fullyQualifiedName", "fromEntity", "fromFqn"))
            if upstream_fqn:
                rows[OPENMETADATA_LINEAGE].append((upstream_fqn, fqn, _text(_pick(upstream, "lineageDetails", "type"))))
    return rows


def _atlan_parse(documents: list[Any]) -> dict[TableSchema, list[tuple[Any, ...]]]:
    tables = (ATLAN_ASSET, ATLAN_FIELD, ATLAN_LINEAGE)
    rows = _rows(tables)
    for asset in _records(documents, "entities", "assets", "records"):
        attrs = asset.get("attributes") if isinstance(asset.get("attributes"), dict) else asset
        guid = _text(_pick(asset, "guid", "id")) or _text(_pick(attrs, "guid", "qualifiedName"))
        if not guid:
            continue
        rows[ATLAN_ASSET].append((
            guid,
            _text(_pick(attrs, "qualifiedName", "qualified_name")),
            _text(_pick(asset, "typeName", "assetType") or _pick(attrs, "typeName", "assetType")),
            _name(attrs),
            _description(attrs),
            _pick(attrs, "ownerUsers", "owner_users", default=[]),
        ))
        related = asset.get("relationshipAttributes") if isinstance(asset.get("relationshipAttributes"), dict) else {}
        for field in _dicts(_pick(related, "columns", "fields", default=[]) or _pick(attrs, "columns", "fields", default=[])):
            field_attrs = field.get("attributes") if isinstance(field.get("attributes"), dict) else field
            field_guid = _text(_pick(field, "guid", "id")) or _text(_pick(field_attrs, "qualifiedName"))
            if field_guid:
                rows[ATLAN_FIELD].append((
                    guid,
                    field_guid,
                    _text(_pick(field_attrs, "qualifiedName", "qualified_name")),
                    _name(field_attrs),
                    _text(_pick(field_attrs, "dataType", "type")),
                    _description(field_attrs),
                ))
        for edge in _dicts(_pick(asset, "lineage", "upstream", default=[])):
            upstream = _text(_pick(edge, "upstreamGuid", "guid", "from"))
            downstream = _text(_pick(edge, "downstreamGuid", "to")) or guid
            if upstream and downstream:
                rows[ATLAN_LINEAGE].append((upstream, downstream, _text(_pick(edge, "type", "relationshipType"))))
    return rows


def _alation_parse(documents: list[Any]) -> dict[TableSchema, list[tuple[Any, ...]]]:
    tables = (ALATION_DATA_SOURCE, ALATION_TABLE, ALATION_COLUMN, ALATION_GLOSSARY_TERM)
    rows = _rows(tables)
    for data_source in _records(documents, "data_sources", "dataSources"):
        data_source_id = _identifier(data_source, "id", "ds_id")
        if data_source_id:
            rows[ALATION_DATA_SOURCE].append((
                data_source_id,
                _text(_pick(data_source, "title", "name")),
                _description(data_source),
                _text(_pick(data_source, "dbtype", "type")),
            ))
    for table in _records(documents, "tables"):
        table_id = _identifier(table, "id", "table_id")
        if table_id:
            rows[ALATION_TABLE].append((
                table_id,
                _text(_pick(table, "ds_id", "data_source_id")),
                _text(_pick(table, "schema_name", "schema")),
                _name(table),
                _description(table),
            ))
        for column in _dicts(table.get("columns")):
            column_id = _identifier(column, "id", "column_id") or f"{table_id}.{_name(column)}"
            if table_id and column_id:
                rows[ALATION_COLUMN].append((
                    column_id,
                    table_id,
                    _name(column),
                    _text(_pick(column, "data_type", "type")),
                    _description(column),
                ))
    for column in _records(documents, "columns"):
        column_id = _identifier(column, "id", "column_id")
        if column_id:
            rows[ALATION_COLUMN].append((
                column_id,
                _text(_pick(column, "table_id")),
                _name(column),
                _text(_pick(column, "data_type", "type")),
                _description(column),
            ))
    for term in _records(documents, "glossary_terms", "terms"):
        term_id = _identifier(term, "id", "term_id")
        if term_id:
            rows[ALATION_GLOSSARY_TERM].append((term_id, _text(_pick(term, "title", "name")), _description(term)))
    return rows


def _collibra_parse(documents: list[Any]) -> dict[TableSchema, list[tuple[Any, ...]]]:
    tables = (COLLIBRA_ASSET, COLLIBRA_ATTRIBUTE, COLLIBRA_RELATION, COLLIBRA_RESPONSIBILITY)
    rows = _rows(tables)
    for asset in _records(documents, "assets", "results"):
        asset_id = _identifier(asset, "id", "assetId")
        if not asset_id:
            continue
        rows[COLLIBRA_ASSET].append((
            asset_id,
            _name(asset),
            _text(_pick(asset, "displayName", "display_name")),
            _text(_pick(asset.get("type", {}) if isinstance(asset.get("type"), dict) else asset, "name", "assetType")),
            _text(_pick(asset.get("domain", {}) if isinstance(asset.get("domain"), dict) else {}, "id")),
            _description(asset),
        ))
        for attr in _dicts(_pick(asset, "attributes", default=[])):
            attr_type = _text(_pick(attr.get("type", {}) if isinstance(attr.get("type"), dict) else attr, "name", "attributeType"))
            if attr_type:
                rows[COLLIBRA_ATTRIBUTE].append((asset_id, attr_type, _text(_pick(attr, "value", "text"))))
        for relation in _dicts(_pick(asset, "relations", "relationships", default=[])):
            target = _text(_pick(relation, "targetId", "target", "to"))
            source = _text(_pick(relation, "sourceId", "source", "from")) or asset_id
            if source and target:
                rows[COLLIBRA_RELATION].append((source, target, _text(_pick(relation, "type", "relationType"))))
        for responsibility in _dicts(_pick(asset, "responsibilities", "owners", default=[])):
            owner_id = _text(_pick(responsibility, "ownerId", "userId", "id"))
            if owner_id:
                rows[COLLIBRA_RESPONSIBILITY].append((asset_id, owner_id, _text(_pick(responsibility, "role", "type"))))
    return rows


def _metabase_parse(documents: list[Any]) -> dict[TableSchema, list[tuple[Any, ...]]]:
    tables = (METABASE_DATABASE, METABASE_TABLE, METABASE_FIELD, METABASE_CARD, METABASE_DASHBOARD)
    rows = _rows(tables)
    for database in _records(documents, "databases"):
        database_id = _identifier(database, "id", "database_id")
        if database_id:
            rows[METABASE_DATABASE].append((database_id, _name(database), _text(database.get("engine")), _description(database)))
        for table in _dicts(database.get("tables")):
            _append_metabase_table(rows, table, database_id)
    for table in _records(documents, "tables"):
        _append_metabase_table(rows, table, _text(_pick(table, "db_id", "database_id")))
    for card in _records(documents, "cards", "questions"):
        card_id = _identifier(card, "id", "card_id")
        if card_id:
            rows[METABASE_CARD].append((
                card_id,
                _text(_pick(card, "database_id", "db_id")),
                _name(card),
                _description(card),
                _pick(card, "dataset_query", "query", default={}),
            ))
    for dashboard in _records(documents, "dashboards"):
        dashboard_id = _identifier(dashboard, "id", "dashboard_id")
        if dashboard_id:
            rows[METABASE_DASHBOARD].append((dashboard_id, _name(dashboard), _description(dashboard)))
    return rows


def _append_metabase_table(rows: dict[TableSchema, list[tuple[Any, ...]]], table: dict[str, Any], database_id: str | None) -> None:
    table_id = _identifier(table, "id", "table_id")
    if not table_id:
        return
    rows[METABASE_TABLE].append((
        table_id,
        database_id,
        _text(_pick(table, "schema", "schema_name")),
        _name(table),
        _description(table),
    ))
    for field in _dicts(table.get("fields")):
        field_id = _identifier(field, "id", "field_id") or f"{table_id}.{_name(field)}"
        if field_id:
            rows[METABASE_FIELD].append((
                field_id,
                table_id,
                _name(field),
                _text(_pick(field, "base_type", "semantic_type", "type")),
                _description(field),
            ))


def _cube_parse(documents: list[Any]) -> dict[TableSchema, list[tuple[Any, ...]]]:
    tables = (CUBE_CUBE, CUBE_MEASURE, CUBE_DIMENSION, CUBE_SEGMENT, CUBE_JOIN)
    rows = _rows(tables)
    for cube in _records(documents, "cubes"):
        cube_name = _name(cube)
        if not cube_name:
            continue
        public = _pick(cube, "public", default=None)
        if public is None:
            public = _pick(cube, "isVisible", default=False)
        public_value = _bool({"value": public}, "value")
        rows[CUBE_CUBE].append((
            cube_name,
            _text(cube.get("title")),
            _description(cube),
            _text(cube.get("sql")),
            public_value,
        ))
        for measure in _dicts(cube.get("measures")):
            measure_name = _name(measure)
            if measure_name:
                rows[CUBE_MEASURE].append((
                    cube_name,
                    measure_name,
                    _text(measure.get("type")),
                    _text(measure.get("sql")),
                    _description(measure),
                ))
        for dimension in _dicts(cube.get("dimensions")):
            dimension_name = _name(dimension)
            if dimension_name:
                rows[CUBE_DIMENSION].append((
                    cube_name,
                    dimension_name,
                    _text(dimension.get("type")),
                    _text(dimension.get("sql")),
                    _description(dimension),
                    _bool(dimension, "primaryKey", "primary_key"),
                ))
        for segment in _dicts(cube.get("segments")):
            segment_name = _name(segment)
            if segment_name:
                rows[CUBE_SEGMENT].append((cube_name, segment_name, _text(segment.get("sql")), _description(segment)))
        joins = cube.get("joins")
        if isinstance(joins, dict):
            join_items = [{"name": name, **value} if isinstance(value, dict) else {"name": name, "sql": value} for name, value in joins.items()]
        else:
            join_items = _dicts(joins)
        for join in join_items:
            join_name = _name(join)
            if join_name:
                rows[CUBE_JOIN].append((
                    cube_name,
                    join_name,
                    _text(join.get("relationship")),
                    _text(join.get("sql")),
                ))
    return rows


SUPPORTED_PROVIDERS: dict[str, Provider] = {
    "powerbi": Provider(
        "powerbi",
        (
            POWERBI_WORKSPACE,
            POWERBI_SEMANTIC_MODEL,
            POWERBI_TABLE,
            POWERBI_COLUMN,
            POWERBI_MEASURE,
            POWERBI_REPORT,
            POWERBI_LINEAGE,
        ),
        _powerbi_parse,
        _summarize("powerbi:", ((POWERBI_SEMANTIC_MODEL, "models"), (POWERBI_MEASURE, "measures"), (POWERBI_REPORT, "reports"))),
    ),
    "tableau": Provider(
        "tableau",
        (TABLEAU_WORKBOOK, TABLEAU_DATASOURCE, TABLEAU_FIELD, TABLEAU_DASHBOARD, TABLEAU_LINEAGE),
        _tableau_parse,
        _summarize("tableau:", ((TABLEAU_WORKBOOK, "workbooks"), (TABLEAU_DATASOURCE, "datasources"), (TABLEAU_FIELD, "fields"))),
    ),
    "dbt_semantic": Provider(
        "dbt_semantic",
        (
            DBT_SEMANTIC_MODEL,
            DBT_SEMANTIC_ENTITY,
            DBT_SEMANTIC_DIMENSION,
            DBT_SEMANTIC_MEASURE,
            DBT_SEMANTIC_METRIC,
        ),
        _dbt_semantic_parse,
        _summarize("dbt-sem:", ((DBT_SEMANTIC_MODEL, "semantic models"), (DBT_SEMANTIC_METRIC, "metrics"))),
    ),
    "datahub": Provider(
        "datahub",
        (DATAHUB_ENTITY, DATAHUB_FIELD, DATAHUB_OWNER, DATAHUB_LINEAGE),
        _datahub_parse,
        _summarize("datahub:", ((DATAHUB_ENTITY, "entities"), (DATAHUB_FIELD, "fields"), (DATAHUB_LINEAGE, "lineage edges"))),
    ),
    "openmetadata": Provider(
        "openmetadata",
        (OPENMETADATA_ENTITY, OPENMETADATA_FIELD, OPENMETADATA_LINEAGE),
        _openmetadata_parse,
        _summarize("openmeta:", ((OPENMETADATA_ENTITY, "entities"), (OPENMETADATA_FIELD, "fields"), (OPENMETADATA_LINEAGE, "lineage edges"))),
    ),
    "atlan": Provider(
        "atlan",
        (ATLAN_ASSET, ATLAN_FIELD, ATLAN_LINEAGE),
        _atlan_parse,
        _summarize("atlan:", ((ATLAN_ASSET, "assets"), (ATLAN_FIELD, "fields"), (ATLAN_LINEAGE, "lineage edges"))),
    ),
    "alation": Provider(
        "alation",
        (ALATION_DATA_SOURCE, ALATION_TABLE, ALATION_COLUMN, ALATION_GLOSSARY_TERM),
        _alation_parse,
        _summarize("alation:", ((ALATION_DATA_SOURCE, "sources"), (ALATION_TABLE, "tables"), (ALATION_GLOSSARY_TERM, "terms"))),
    ),
    "collibra": Provider(
        "collibra",
        (COLLIBRA_ASSET, COLLIBRA_ATTRIBUTE, COLLIBRA_RELATION, COLLIBRA_RESPONSIBILITY),
        _collibra_parse,
        _summarize("collibra:", ((COLLIBRA_ASSET, "assets"), (COLLIBRA_RELATION, "relations"), (COLLIBRA_RESPONSIBILITY, "responsibilities"))),
    ),
    "metabase": Provider(
        "metabase",
        (METABASE_DATABASE, METABASE_TABLE, METABASE_FIELD, METABASE_CARD, METABASE_DASHBOARD),
        _metabase_parse,
        _summarize("metabase:", ((METABASE_DATABASE, "databases"), (METABASE_CARD, "cards"), (METABASE_DASHBOARD, "dashboards"))),
    ),
    "cube": Provider(
        "cube",
        (CUBE_CUBE, CUBE_MEASURE, CUBE_DIMENSION, CUBE_SEGMENT, CUBE_JOIN),
        _cube_parse,
        _summarize("cube:", ((CUBE_CUBE, "cubes"), (CUBE_MEASURE, "measures"), (CUBE_DIMENSION, "dimensions"))),
    ),
}
