"""LookML connector: writes agents.lookml_* from LookML files."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .destinations import Column, Destination, TableSchema, open_destination
from .root import upsert_provider_root
from .views import create_context_views

__all__ = ["run"]

LOOKML_VIEW = TableSchema(
    "agents.lookml_view",
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
    "agents.lookml_dimension",
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
    "agents.lookml_measure",
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
    "agents.lookml_explore",
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

_BLOCK_RE = re.compile(
    r"\b(view|explore|dimension|dimension_group|measure)\s*:\s*([A-Za-z_][\w.]*)\s*\{"
)
_PROP_RE = re.compile(r"^\s*([A-Za-z_][\w]*)\s*:\s*(.*)$")
_FIELD_KINDS = {"dimension", "dimension_group", "measure"}


@dataclass(frozen=True)
class _Block:
    kind: str
    name: str
    body: str
    start: int
    end: int


def run(cfg: dict) -> None:
    lookml_dir = Path(cfg["metadata_connection"]["path"])
    files = _load_lookml_files(lookml_dir)
    with open_destination(cfg) as dest:
        upsert_provider_root(dest, "lookml")
        _create_tables(dest)
        _ingest(dest, files, lookml_dir)
        create_context_views(dest)


def _load_lookml_files(lookml_dir: Path) -> list[Path]:
    files = sorted(lookml_dir.glob("**/*.lkml"))
    if not files:
        raise FileNotFoundError(f"no *.lkml files found in {lookml_dir}")
    return files


def _create_tables(dest: Destination) -> None:
    dest.replace_table(LOOKML_VIEW)
    dest.replace_table(LOOKML_DIMENSION)
    dest.replace_table(LOOKML_MEASURE)
    dest.replace_table(LOOKML_EXPLORE)


def _ingest(dest: Destination, files: list[Path], base_dir: Path) -> None:
    views, dimensions, measures, explores = [], [], [], []

    for file_path in files:
        rel_path = str(file_path.relative_to(base_dir))
        text = _strip_comments(file_path.read_text())

        for view in _iter_blocks(text, {"view"}):
            field_blocks = list(_iter_blocks(view.body, _FIELD_KINDS))
            props = _parse_properties(_mask_ranges(view.body, field_blocks))
            views.append((
                view.name,
                _string(props.get("sql_table_name")),
                _string(props.get("label")),
                _string(props.get("description")),
                _string(props.get("ai_context")),
                rel_path,
            ))

            for field in field_blocks:
                field_props = _parse_properties(field.body)
                if field.kind == "measure":
                    measures.append((
                        view.name,
                        field.name,
                        _string(field_props.get("type")),
                        _string(field_props.get("sql")),
                        _string(field_props.get("description")),
                        _string(field_props.get("ai_context")),
                        _string(field_props.get("filters")),
                    ))
                else:
                    dimensions.append((
                        view.name,
                        field.name,
                        field.kind,
                        _string(field_props.get("type")),
                        _string(field_props.get("sql")),
                        _string(field_props.get("description")),
                        _string(field_props.get("ai_context")),
                        _bool(field_props.get("primary_key")),
                    ))

        for explore in _iter_blocks(text, {"explore"}):
            props = _parse_properties(explore.body)
            explores.append((
                explore.name,
                _string(props.get("from")) or explore.name,
                _string(props.get("label")),
                _string(props.get("description")),
                _string(props.get("ai_context")),
                rel_path,
            ))

    if views:
        dest.insert_rows(LOOKML_VIEW, views)
    if dimensions:
        dest.insert_rows(LOOKML_DIMENSION, dimensions)
    if measures:
        dest.insert_rows(LOOKML_MEASURE, measures)
    if explores:
        dest.insert_rows(LOOKML_EXPLORE, explores)

    print(
        f"  lookml:   {len(views)} views, {len(dimensions)} dimensions, "
        f"{len(measures)} measures, {len(explores)} explores"
    )


def _strip_comments(text: str) -> str:
    out = []
    quote: str | None = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < len(text):
                i += 1
                out.append(text[i])
            elif ch == quote:
                quote = None
        elif ch in {"'", '"'}:
            quote = ch
            out.append(ch)
        elif ch == "#":
            while i < len(text) and text[i] != "\n":
                i += 1
            if i < len(text):
                out.append("\n")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _iter_blocks(text: str, kinds: Iterable[str]) -> Iterable[_Block]:
    wanted = set(kinds)
    pos = 0
    while match := _BLOCK_RE.search(text, pos):
        kind, name = match.group(1), match.group(2)
        open_brace = match.end() - 1
        close_brace = _matching_brace(text, open_brace)
        if kind in wanted:
            yield _Block(
                kind=kind,
                name=name,
                body=text[open_brace + 1 : close_brace],
                start=match.start(),
                end=close_brace + 1,
            )
        pos = close_brace + 1


def _matching_brace(text: str, open_brace: int) -> int:
    depth = 0
    quote: str | None = None
    i = open_brace
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in {"'", '"'}:
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unterminated LookML block")


def _mask_ranges(text: str, blocks: list[_Block]) -> str:
    chars = list(text)
    for block in blocks:
        for i in range(block.start, block.end):
            chars[i] = "\n" if chars[i] == "\n" else " "
    return "".join(chars)


def _parse_properties(text: str) -> dict[str, Any]:
    props: dict[str, Any] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        match = _PROP_RE.match(lines[i])
        if not match:
            i += 1
            continue

        key, value = match.group(1), match.group(2).strip()
        if key == "sql" and ";;" not in value:
            while i + 1 < len(lines):
                i += 1
                value += "\n" + lines[i].strip()
                if ";;" in lines[i]:
                    break
        props[key] = _clean_value(value)
        i += 1
    return props


def _clean_value(value: str) -> str:
    value = value.strip()
    if ";;" in value:
        value = value.split(";;", 1)[0].strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value


def _string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).lower() in {"yes", "true"}
