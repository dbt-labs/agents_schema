"""Cube connector: writes agents.cube* from metadata exports."""
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

TABLES = (CUBE_CUBE, CUBE_MEASURE, CUBE_DIMENSION, CUBE_SEGMENT, CUBE_JOIN)
SUMMARY = _summarize("cube:", ((CUBE_CUBE, "cubes"), (CUBE_MEASURE, "measures"), (CUBE_DIMENSION, "dimensions")))


def run(cfg: dict[str, Any]) -> None:
    run_connector(cfg, "cube", TABLES, _cube_parse, SUMMARY)


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
