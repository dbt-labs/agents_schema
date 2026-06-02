"""dbt Semantic Layer connector: writes agents.dbt_semantic* from metadata exports."""
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

TABLES = (DBT_SEMANTIC_MODEL, DBT_SEMANTIC_ENTITY, DBT_SEMANTIC_DIMENSION, DBT_SEMANTIC_MEASURE, DBT_SEMANTIC_METRIC)
SUMMARY = _summarize("dbt-sem:", ((DBT_SEMANTIC_MODEL, "semantic models"), (DBT_SEMANTIC_METRIC, "metrics")))


def run(cfg: dict[str, Any]) -> None:
    run_connector(cfg, "dbt_semantic", TABLES, _dbt_semantic_parse, SUMMARY)


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
