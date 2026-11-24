"""LookML connector: writes AGENTS.LOOKML_* from LookML files."""
from __future__ import annotations

import contextlib
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lkml

from .config import warehouse_type
from .destinations import Column, Destination, TableSchema, open_destination
from .root import upsert_provider_root
from .skills import publish_builtin_skill

__all__ = ["run"]

LOOKML_VIEW = TableSchema(
    "AGENTS.LOOKML_VIEW",
    (
        Column("name", "varchar", nullable=False),
        Column("sql_table_name", "varchar"),
        Column("label", "varchar"),
        Column("description", "text"),
        Column("ai_context", "text"),
        Column("file_path", "varchar"),
    ),
    primary_key=("name",),
)
LOOKML_DIMENSION = TableSchema(
    "AGENTS.LOOKML_DIMENSION",
    (
        Column("view_name", "varchar", nullable=False),
        Column("field_name", "varchar", nullable=False),
        Column("field_kind", "varchar", nullable=False),
        Column("type", "varchar"),
        Column("sql", "text"),
        Column("description", "text"),
        Column("ai_context", "text"),
        Column("primary_key", "boolean"),
    ),
    primary_key=("view_name", "field_name"),
)
LOOKML_MEASURE = TableSchema(
    "AGENTS.LOOKML_MEASURE",
    (
        Column("view_name", "varchar", nullable=False),
        Column("measure_name", "varchar", nullable=False),
        Column("type", "varchar"),
        Column("sql", "text"),
        Column("description", "text"),
        Column("ai_context", "text"),
        Column("filters", "text"),
    ),
    primary_key=("view_name", "measure_name"),
)
LOOKML_EXPLORE = TableSchema(
    "AGENTS.LOOKML_EXPLORE",
    (
        Column("name", "varchar", nullable=False),
        Column("from_view", "varchar"),
        Column("label", "varchar"),
        Column("description", "text"),
        Column("ai_context", "text"),
        Column("file_path", "varchar"),
    ),
    primary_key=("name",),
)


# A `sql` value that contains the start of another block means a missing `;;` made the parser swallow what follows.
_SWALLOWED_BLOCK = re.compile(r"(?m)^\s*(?:view|explore|dimension|dimension_group|measure|filter|parameter)\s*:\s*[\w.+]+\s*\{")


@contextlib.contextmanager
def _quiet_lkml():
    """Silence lkml's warnings while it parses one file.

    lkml warns for every repeated top-level key (a model file often repeats `include`), which is noise here.
    A file it cannot parse raises instead, so nothing useful is lost. The level is restored afterwards, so
    importing this module does not change logging for the rest of the process.
    """
    logger = logging.getLogger("lkml")
    previous = logger.level
    logger.setLevel(logging.ERROR)
    try:
        yield
    finally:
        logger.setLevel(previous)


def _warn(message: str) -> None:
    """A warning on stderr, plus a GitHub annotation when running in Actions so it is visible on the run page."""
    print(f"agents-schema: warning: {message}", file=sys.stderr)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::warning title=Agents Schema LookML::{escaped}")


_FIELD_KEYS = (("dimension", "dimensions"), ("dimension_group", "dimension_groups"))
_VIEW_PROPS = ("sql_table_name", "label", "description", "ai_context")
_EXPLORE_PROPS = ("from", "label", "description", "ai_context")
_FIELD_PROPS = ("type", "sql", "description", "ai_context", "primary_key")


def run(cfg: dict) -> None:
    lookml_dir = Path(cfg["metadata_connection"]["path"])
    files = _load_lookml_files(lookml_dir)
    rows = _collect(files, lookml_dir)  # parse first: a bad file must not leave emptied tables behind
    with open_destination(cfg) as dest:
        upsert_provider_root(dest, "lookml")
        _create_tables(dest)
        _write(dest, rows)
        publish_builtin_skill(dest, warehouse_type(cfg))


def _load_lookml_files(lookml_dir: Path) -> list[Path]:
    files = sorted(path for path in lookml_dir.glob("**/*.lkml") if path.is_file())
    if not files:
        raise FileNotFoundError(f"no *.lkml files found in {lookml_dir}")
    return files


def _create_tables(dest: Destination) -> None:
    dest.replace_table(LOOKML_VIEW)
    dest.replace_table(LOOKML_DIMENSION)
    dest.replace_table(LOOKML_MEASURE)
    dest.replace_table(LOOKML_EXPLORE)


@dataclass
class _Rows:
    """Parsed LookML, keyed by primary key so refinements can merge into their base definitions."""

    skipped: int = 0  # files that could not be parsed
    views: dict[str, dict[str, str]] = field(default_factory=dict)
    dimensions: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)
    measures: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)
    explores: dict[str, dict[str, str]] = field(default_factory=dict)


def _ingest(dest: Destination, files: list[Path], base_dir: Path) -> None:
    _write(dest, _collect(files, base_dir))


def _collect(files: list[Path], base_dir: Path) -> _Rows:
    rows = _Rows()
    documents: list[tuple[str, dict]] = []
    for file_path in files:
        rel_path = str(file_path.relative_to(base_dir))
        try:
            # utf-8-sig: a byte-order mark (common from Windows editors) would otherwise become part of the first key
            text = file_path.read_text(encoding="utf-8-sig")
        except OSError as e:
            raise ValueError(f"cannot read {rel_path}: {e}") from e
        except ValueError as e:  # UnicodeDecodeError: not UTF-8
            rows.skipped += 1
            _warn(f"skipping {rel_path}: could not read it as UTF-8 text: {e}")
            continue
        try:
            with _quiet_lkml():
                documents.append((rel_path, lkml.load(text)))
        except (SyntaxError, KeyError, ValueError, RecursionError) as e:  # lkml's own parse failures
            rows.skipped += 1
            _warn(f"skipping {rel_path}: could not parse LookML: {e}")
    if files and not documents:
        raise ValueError(f"none of the {len(files)} LookML files in {base_dir} could be parsed")

    views = [(view, rel_path) for rel_path, doc in documents for view in doc.get("views", [])]
    explores = [(explore, rel_path) for rel_path, doc in documents for explore in doc.get("explores", [])]

    # Base definitions first, then refinements (`+name`), each in file order, so a refinement
    # always layers on top of its base regardless of which file sorts first.
    for view, rel_path in sorted(views, key=lambda item: _is_refinement(item[0])):
        _merge_view(rows, view, rel_path)
    for explore, rel_path in sorted(explores, key=lambda item: _is_refinement(item[0])):
        _merge_explore(rows, explore, rel_path)
    return rows


def _is_refinement(block: dict) -> bool:
    return str(block.get("name") or "").startswith("+")


def _block_name(block: dict, kind: str, rel_path: str) -> str | None:
    """The block's name without a refinement's `+`, or None (with a warning) for a block that has none."""
    name = block.get("name")
    if not isinstance(name, str) or not name.lstrip("+"):
        _warn(f"{rel_path}: skipping a {kind} block without a name")
        return None
    return name.lstrip("+")


def _merge_view(rows: _Rows, view: dict, rel_path: str) -> None:
    if (name := _block_name(view, "view", rel_path)) is None:
        return
    refinement = _is_refinement(view)
    props = {key: text for key in _VIEW_PROPS if (text := _text(view.get(key))) is not None}
    if refinement and name in rows.views:
        rows.views[name].update(props)
    else:
        if refinement:
            _warn(
                f"{rel_path}: view +{name} refines a view that is not defined in any ingested file "
                "(or whose file could not be parsed); it is kept with only the refined properties"
            )
        elif name in rows.views:
            # A second full definition of the same view (Looker rejects this): the later one replaces
            # the earlier one entirely instead of inheriting its fields.
            for table in (rows.dimensions, rows.measures):
                for key in [key for key in table if key[0] == name]:
                    del table[key]
        rows.views[name] = {**props, "file_path": rel_path}

    for kind, key in _FIELD_KEYS:
        for field_block in view.get(key, []):
            if (field_name := _block_name(field_block, kind, rel_path)) is None:
                continue
            field_props = _field_props(field_block)
            _check_sql(field_props, rel_path, name, field_name)
            merged = {**rows.dimensions.get((name, field_name), {}), **field_props, "field_kind": kind}
            rows.dimensions[(name, field_name)] = merged
    for measure in view.get("measures", []):
        if (measure_name := _block_name(measure, "measure", rel_path)) is None:
            continue
        props = _field_props(measure)
        _check_sql(props, rel_path, name, measure_name)
        if (filters := _filters(measure)) is not None:
            props["filters"] = filters
        rows.measures[(name, measure_name)] = {**rows.measures.get((name, measure_name), {}), **props}


def _check_sql(props: dict[str, str], rel_path: str, view_name: str, field_name: str) -> None:
    if _SWALLOWED_BLOCK.search(props.get("sql", "")):
        _warn(
            f"{rel_path}: the sql of {view_name}.{field_name} contains what looks like another block; "
            "a missing `;;` may have made the parser swallow the definitions that follow"
        )


def _merge_explore(rows: _Rows, explore: dict, rel_path: str) -> None:
    if (name := _block_name(explore, "explore", rel_path)) is None:
        return
    refinement = _is_refinement(explore)
    props = {key: text for key in _EXPLORE_PROPS if (text := _text(explore.get(key))) is not None}
    if refinement and name in rows.explores:
        rows.explores[name].update(props)
    else:
        if refinement:
            _warn(
                f"{rel_path}: explore +{name} refines an explore that is not defined in any ingested file "
                "(or whose file could not be parsed); it is kept with only the refined properties"
            )
        rows.explores[name] = {**props, "file_path": rel_path}


def _field_props(block: dict) -> dict[str, str]:
    return {key: text for key in _FIELD_PROPS if (text := _text(block.get(key))) is not None}


def _filters(measure: dict) -> str | None:
    """A measure's filters as one readable string, whichever syntax the file used.

    The inline form `filters: [status: "complete", region: "EU"]` and the block form
    `filters: { field: status value: "complete" }` both become `field: "value"` pairs.
    """
    groups = measure.get("filters__all") or []
    if not groups and isinstance(measure.get("filters"), list):
        groups = [measure["filters"]]
    pairs = []
    for group in groups:
        for entry in group if isinstance(group, list) else [group]:
            if not isinstance(entry, dict):
                continue
            if set(entry) == {"field", "value"}:
                pairs.append(f'{entry["field"]}: "{entry["value"]}"')
            else:
                pairs.extend(f'{key}: "{value}"' for key, value in entry.items())
    return ", ".join(pairs) or None


def _text(value: Any) -> str | None:
    """A property as clean text: lines trimmed (continuation lines are indented in the source), ends stripped."""
    if not isinstance(value, str):
        return None
    return "\n".join(line.strip() for line in value.strip().splitlines())


def _write(dest: Destination, rows: _Rows) -> None:
    views = [
        (
            name,
            _string(p.get("sql_table_name")),
            _string(p.get("label")),
            _string(p.get("description")),
            _string(p.get("ai_context")),
            p["file_path"],
        )
        for name, p in rows.views.items()
    ]
    dimensions = [
        (
            view_name,
            field_name,
            p["field_kind"],
            _string(p.get("type")),
            _string(p.get("sql")),
            _string(p.get("description")),
            _string(p.get("ai_context")),
            _bool(p.get("primary_key")),
        )
        for (view_name, field_name), p in rows.dimensions.items()
    ]
    measures = [
        (
            view_name,
            measure_name,
            _string(p.get("type")),
            _string(p.get("sql")),
            _string(p.get("description")),
            _string(p.get("ai_context")),
            _string(p.get("filters")),
        )
        for (view_name, measure_name), p in rows.measures.items()
    ]
    explores = [
        (
            name,
            _string(p.get("from")) or name,
            _string(p.get("label")),
            _string(p.get("description")),
            _string(p.get("ai_context")),
            p["file_path"],
        )
        for name, p in rows.explores.items()
    ]

    if views:
        dest.insert_rows(LOOKML_VIEW, views)
    if dimensions:
        dest.insert_rows(LOOKML_DIMENSION, dimensions)
    if measures:
        dest.insert_rows(LOOKML_MEASURE, measures)
    if explores:
        dest.insert_rows(LOOKML_EXPLORE, explores)

    skipped = f", {rows.skipped} files skipped (see the warnings)" if rows.skipped else ""
    print(
        f"  lookml:   {len(views)} views, {len(dimensions)} dimensions, "
        f"{len(measures)} measures, {len(explores)} explores{skipped}"
    )




def _string(value: Any) -> str | None:
    return None if value is None else str(value)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"yes", "true"} if value is not None else False
