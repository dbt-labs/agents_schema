"""Omni connector: writes AGENTS.OMNI_* from Omni YAML files."""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .inputs import parse_input
from .destinations import Column, Destination, TableSchema, open_destination
from .root import upsert_provider_root

__all__ = ["run"]

_REF_RE = re.compile(r"#\s*Reference this view as\s+(\S+)")

OMNI_VIEW = TableSchema(
    "AGENTS.OMNI_VIEW",
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
    "AGENTS.OMNI_DIMENSION",
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
    "AGENTS.OMNI_MEASURE",
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
    "AGENTS.OMNI_TOPIC",
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
    "AGENTS.OMNI_TOPIC_JOIN",
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
    rows = parse_input("omni", _collect, omni_dir)  # parse first: nothing is replaced in the warehouse if reading fails
    if not rows.found:
        raise FileNotFoundError(f"no *.view.yaml or *.topic.yaml files found in {omni_dir}")
    if not rows.usable:
        raise ValueError(f"none of the {rows.found} Omni files in {omni_dir} could be read; see the warnings above")
    with open_destination(cfg) as dest:
        upsert_provider_root(dest, "omni")
        _create_tables(dest)
        _write(dest, rows)


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


@dataclass
class _Rows:
    found: int = 0  # *.view.yaml / *.topic.yaml files seen
    usable: int = 0  # ... of which could be read
    views: list = field(default_factory=list)
    dimensions: list = field(default_factory=list)
    measures: list = field(default_factory=list)
    topics: list = field(default_factory=list)
    topic_joins: list = field(default_factory=list)


def _ingest(dest: Destination, omni_dir: Path) -> None:
    _write(dest, _collect(omni_dir))


def _read_yaml(path: Path, omni_dir: Path) -> dict | None:
    """Parse one Omni YAML file. Unusable files are skipped with a warning, never silently."""
    rel = path.relative_to(omni_dir)
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
    except (yaml.YAMLError, ValueError) as e:  # ValueError: a YAML date such as 2001-13-45
        reason = str(e).strip().splitlines()[0]
        print(f"  omni: warning: skipped {rel}: invalid YAML ({reason})", file=sys.stderr)
        return None
    if doc is None:  # an empty or comment-only file is kept as an empty view, as before
        doc = {}
    if not isinstance(doc, dict):
        print(f"  omni: warning: skipped {rel}: expected a YAML mapping, got {type(doc).__name__}", file=sys.stderr)
        return None
    return doc


def _collect(omni_dir: Path) -> _Rows:
    rows = _Rows()

    for path in sorted(p for p in omni_dir.glob("**/*.view.yaml") if p.is_file()):
        rel = str(path.relative_to(omni_dir))
        rows.found += 1
        view_name = _view_name_from_file(path, omni_dir)
        doc = _read_yaml(path, omni_dir)
        if doc is None:
            continue
        rows.usable += 1

        rows.views.append((
            view_name,
            doc.get("schema"),
            doc.get("table_name"),
            doc.get("label"),
            doc.get("description"),
            rel,
        ))

        for field_name, field_def in (doc.get("dimensions") or {}).items():
            if not isinstance(field_def, dict):
                field_def = {}
            rows.dimensions.append((
                view_name,
                field_name,
                field_def.get("label"),
                field_def.get("sql"),
                field_def.get("format"),
                field_def.get("description"),
                bool(field_def.get("primary_key")),
            ))

        for measure_name, measure in (doc.get("measures") or {}).items():
            if not isinstance(measure, dict):
                measure = {}
            rows.measures.append((
                view_name,
                measure_name,
                measure.get("label"),
                measure.get("aggregate_type"),
                measure.get("sql"),
                measure.get("description"),
            ))

    for path in sorted(p for p in omni_dir.glob("**/*.topic.yaml") if p.is_file()):
        rel = str(path.relative_to(omni_dir))
        rows.found += 1
        topic_name = _topic_name_from_file(path)
        doc = _read_yaml(path, omni_dir)
        if doc is None:
            continue
        rows.usable += 1

        base_view = doc.get("base_view") or ""
        rows.topics.append((
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
                rows.topic_joins.append((topic_name, from_view, to_view))

    return rows


def _write(dest: Destination, rows: _Rows) -> None:
    if rows.views:
        dest.insert_rows(OMNI_VIEW, rows.views)
    if rows.dimensions:
        dest.insert_rows(OMNI_DIMENSION, rows.dimensions)
    if rows.measures:
        dest.insert_rows(OMNI_MEASURE, rows.measures)
    if rows.topics:
        dest.insert_rows(OMNI_TOPIC, rows.topics)
    if rows.topic_joins:
        dest.insert_rows(OMNI_TOPIC_JOIN, rows.topic_joins)

    print(
        f"  omni:     {len(rows.views)} views, {len(rows.dimensions)} dimensions, "
        f"{len(rows.measures)} measures, {len(rows.topics)} topics, {len(rows.topic_joins)} joins"
    )
