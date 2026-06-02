"""Power BI connector: writes agents.powerbi* from metadata exports."""
from __future__ import annotations

from typing import Any

from .destinations import Column, TableSchema
from .metadata_helpers import (
    _bool,
    _description,
    _dicts,
    _identifier,
    _name,
    _owner_name,
    _pick,
    _platform,
    _records,
    _rows,
    _summarize,
    _text,
    run_connector,
)

__all__ = ["run"]

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

TABLES = (POWERBI_WORKSPACE, POWERBI_SEMANTIC_MODEL, POWERBI_TABLE, POWERBI_COLUMN, POWERBI_MEASURE, POWERBI_REPORT, POWERBI_LINEAGE)
SUMMARY = _summarize("powerbi:", ((POWERBI_SEMANTIC_MODEL, "models"), (POWERBI_MEASURE, "measures"), (POWERBI_REPORT, "reports")))


def run(cfg: dict[str, Any]) -> None:
    run_connector(cfg, "powerbi", TABLES, _powerbi_parse, SUMMARY)


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
