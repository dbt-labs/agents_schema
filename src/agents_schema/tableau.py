"""Tableau connector: writes agents.tableau* from metadata exports."""
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

TABLES = (TABLEAU_WORKBOOK, TABLEAU_DATASOURCE, TABLEAU_FIELD, TABLEAU_DASHBOARD, TABLEAU_LINEAGE)
SUMMARY = _summarize("tableau:", ((TABLEAU_WORKBOOK, "workbooks"), (TABLEAU_DATASOURCE, "datasources"), (TABLEAU_FIELD, "fields")))


def run(cfg: dict[str, Any]) -> None:
    run_connector(cfg, "tableau", TABLES, _tableau_parse, SUMMARY)


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
