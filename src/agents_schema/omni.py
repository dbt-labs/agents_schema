"""Omni connector: writes agents.omni_* from Omni YAML files."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from .destinations import Column, Destination, TableSchema, open_destination
from .root import upsert_provider_root

__all__ = ["run"]

_REF_RE = re.compile(r"#\s*Reference this view as\s+(\S+)")

OMNI_VIEW = TableSchema(
    "agents.omni_view",
    (
        Column("view_name", "varchar", nullable=False),
        Column("schema", "varchar"),
        Column("table_name", "varchar"),
        Column("label", "varchar"),
        Column("description", "text"),
        Column("file_path", "varchar"),
    ),
    primary_key=("view_name",),
)
OMNI_DIMENSION = TableSchema(
    "agents.omni_dimension",
    (
        Column("view_name", "varchar", nullable=False),
        Column("field_name", "varchar", nullable=False),
        Column("label", "varchar"),
        Column("sql", "text"),
        Column("format", "varchar"),
        Column("description", "text"),
        Column("primary_key", "boolean"),
    ),
    primary_key=("view_name", "field_name"),
)
OMNI_MEASURE = TableSchema(
    "agents.omni_measure",
    (
        Column("view_name", "varchar", nullable=False),
        Column("measure_name", "varchar", nullable=False),
        Column("label", "varchar"),
        Column("aggregate_type", "varchar"),
        Column("sql", "text"),
        Column("description", "text"),
    ),
    primary_key=("view_name", "measure_name"),
)
OMNI_TOPIC = TableSchema(
    "agents.omni_topic",
    (
        Column("topic_name", "varchar", nullable=False),
        Column("base_view", "varchar"),
        Column("label", "varchar"),
        Column("group_label", "varchar"),
        Column("description", "text"),
        Column("ai_context", "text"),
        Column("file_path", "varchar"),
    ),
    primary_key=("topic_name",),
)
OMNI_TOPIC_JOIN = TableSchema(
    "agents.omni_topic_join",
    (
        Column("topic_name", "varchar", nullable=False),
        Column("from_view", "varchar", nullable=False),
        Column("to_view", "varchar", nullable=False),
    ),
    primary_key=("topic_name", "from_view", "to_view"),
)


def run(cfg: dict) -> None:
    omni_dir = Path(cfg["metadata_connection"]["path"])
    if not omni_dir.is_dir():
        raise FileNotFoundError(f"omni directory not found: {omni_dir}")
    with open_destination(cfg) as dest:
        upsert_provider_root(dest, "omni")
        _create_tables(dest)
        _ingest(dest, omni_dir)


def _create_tables(dest: Destination) -> None:
    dest.replace_table(OMNI_VIEW)
    dest.replace_table(OMNI_DIMENSION)
    dest.replace_table(OMNI_MEASURE)
    dest.replace_table(OMNI_TOPIC)
    dest.replace_table(OMNI_TOPIC_JOIN)


def _view_name_from_file(path: Path, base_dir: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines()[:5]:
        m = _REF_RE.search(line)
        if m:
            return m.group(1)
    # Fallback: {schema}__{stem} derived from path
    rel = path.relative_to(base_dir)
    parts = rel.parts
    name = parts[-1]
    if name.endswith(".view.yaml"):
        name = name[: -len(".view.yaml")]
    if len(parts) > 1:
        return f"{parts[-2]}__{name}"
    return name


def _topic_name_from_file(path: Path) -> str:
    name = path.name
    if name.endswith(".topic.yaml"):
        return name[: -len(".topic.yaml")]
    return name


def _collect_joins(joins: dict, parent: str, seen: set, result: list) -> None:
    for to_view, children in joins.items():
        edge = (parent, to_view)
        if edge not in seen:
            seen.add(edge)
            result.append(edge)
        if isinstance(children, dict) and children:
            _collect_joins(children, to_view, seen, result)


def _ingest(dest: Destination, omni_dir: Path) -> None:
    views, dimensions, measures = [], [], []
    topics, topic_joins = [], []

    for path in sorted(omni_dir.glob("**/*.view.yaml")):
        rel = str(path.relative_to(omni_dir))
        raw = path.read_text(encoding="utf-8", errors="replace")
        view_name = _view_name_from_file(path, omni_dir)
        try:
            doc = yaml.safe_load(raw) or {}
        except yaml.YAMLError:
            continue

        views.append((
            view_name,
            doc.get("schema"),
            doc.get("table_name"),
            doc.get("label"),
            doc.get("description"),
            rel,
        ))

        for field_name, field in (doc.get("dimensions") or {}).items():
            if not isinstance(field, dict):
                field = {}
            dimensions.append((
                view_name,
                field_name,
                field.get("label"),
                field.get("sql"),
                field.get("format"),
                field.get("description"),
                bool(field.get("primary_key")),
            ))

        for measure_name, measure in (doc.get("measures") or {}).items():
            if not isinstance(measure, dict):
                measure = {}
            measures.append((
                view_name,
                measure_name,
                measure.get("label"),
                measure.get("aggregate_type"),
                measure.get("sql"),
                measure.get("description"),
            ))

    for path in sorted(omni_dir.glob("**/*.topic.yaml")):
        rel = str(path.relative_to(omni_dir))
        topic_name = _topic_name_from_file(path)
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
        except yaml.YAMLError:
            continue

        base_view = doc.get("base_view") or ""
        topics.append((
            topic_name,
            base_view,
            doc.get("label"),
            doc.get("group_label"),
            doc.get("description"),
            doc.get("ai_context"),
            rel,
        ))

        joins_dict = doc.get("joins")
        if isinstance(joins_dict, dict) and joins_dict:
            seen: set[tuple[str, str]] = set()
            edges: list[tuple[str, str]] = []
            _collect_joins(joins_dict, base_view, seen, edges)
            for from_view, to_view in edges:
                topic_joins.append((topic_name, from_view, to_view))

    if views:
        dest.insert_rows(OMNI_VIEW, views)
    if dimensions:
        dest.insert_rows(OMNI_DIMENSION, dimensions)
    if measures:
        dest.insert_rows(OMNI_MEASURE, measures)
    if topics:
        dest.insert_rows(OMNI_TOPIC, topics)
    if topic_joins:
        dest.insert_rows(OMNI_TOPIC_JOIN, topic_joins)

    print(
        f"  omni:     {len(views)} views, {len(dimensions)} dimensions, "
        f"{len(measures)} measures, {len(topics)} topics, {len(topic_joins)} joins"
    )
