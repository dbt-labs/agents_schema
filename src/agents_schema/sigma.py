"""Sigma connector: writes agents.sigma_* from Sigma data model YAML files."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .destinations import Column, Destination, TableSchema, open_destination
from .root import upsert_provider_root

__all__ = ["run"]

SIGMA_DATA_MODEL = TableSchema(
    "agents.sigma_data_model",
    (
        Column("source_file", "varchar", nullable=False),
        Column("name", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("source_file",),
)
SIGMA_ELEMENT = TableSchema(
    "agents.sigma_element",
    (
        Column("source_path", "varchar", nullable=False),
        Column("source_file", "varchar", nullable=False),
        Column("page_name", "varchar", nullable=False),
        Column("element_name", "varchar"),
        Column("connection_id", "varchar"),
        Column("description", "text"),
    ),
    primary_key=("source_path",),
)
SIGMA_COLUMN = TableSchema(
    "agents.sigma_column",
    (
        Column("source_path", "varchar", nullable=False),
        Column("name", "varchar", nullable=False),
        Column("kind", "varchar", nullable=False),
        Column("formula", "text"),
        Column("description", "text"),
    ),
    primary_key=("source_path", "name"),
)
SIGMA_METRIC = TableSchema(
    "agents.sigma_metric",
    (
        Column("source_path", "varchar", nullable=False),
        Column("name", "varchar", nullable=False),
        Column("formula", "text"),
        Column("description", "text"),
    ),
    primary_key=("source_path", "name"),
)

_SIMPLE_METRIC_RE = re.compile(
    r"^(Sum|Avg|CountDistinct|Count|Min|Max)\(\[[^\[\]]+\]\)$"
)
_FORMULA_COL_NAME_RE = re.compile(r"^\[[^\[\]/]+/([^\[\]]+)\]$")


def run(cfg: dict) -> None:
    sigma_dir = Path(cfg["metadata_connection"]["path"])
    files = _load_sigma_files(sigma_dir)
    with open_destination(cfg) as dest:
        upsert_provider_root(dest, "sigma")
        _create_tables(dest)
        _ingest(dest, files, sigma_dir)


def _load_sigma_files(sigma_dir: Path) -> list[Path]:
    files = sorted(sigma_dir.glob("**/*.sigma.yaml"))
    if not files:
        raise FileNotFoundError(f"no *.sigma.yaml files found in {sigma_dir}")
    return files


def _create_tables(dest: Destination) -> None:
    dest.replace_table(SIGMA_DATA_MODEL)
    dest.replace_table(SIGMA_ELEMENT)
    dest.replace_table(SIGMA_COLUMN)
    dest.replace_table(SIGMA_METRIC)


def _ingest(dest: Destination, files: list[Path], sigma_dir: Path) -> None:
    data_models, elements, columns, metrics = [], [], [], []
    seen_element_paths: set[str] = set()

    for file_path in files:
        rel_path = str(file_path.relative_to(sigma_dir))
        model = yaml.safe_load(file_path.read_text())
        if not isinstance(model, dict):
            raise ValueError(f"{rel_path}: expected a YAML mapping, got {type(model).__name__}")

        data_models.append((
            rel_path,
            model.get("name"),
            model.get("description"),
        ))

        for page in model.get("pages", []):
            page_name = page.get("name", "")

            for element in page.get("elements", []):
                if element.get("kind") != "table":
                    continue

                src = element.get("source")
                src_path = _source_path(src)
                if not src_path or src_path in seen_element_paths:
                    continue
                seen_element_paths.add(src_path)

                elements.append((
                    src_path,
                    rel_path,
                    page_name,
                    element.get("name"),
                    src.get("connectionId"),
                    element.get("description"),
                ))

                for col in element.get("columns", []):
                    col_name = _col_display_name(col)
                    if not col_name:
                        continue
                    formula = col.get("formula")
                    columns.append((
                        src_path,
                        col_name,
                        "direct" if _is_direct_formula(formula or "") else "computed",
                        formula,
                        col.get("description"),
                    ))

                for metric in element.get("metrics", []):
                    formula = metric.get("formula")
                    if not _is_simple_metric(formula or ""):
                        continue
                    metric_name = metric.get("name")
                    if not metric_name:
                        continue
                    metrics.append((
                        src_path,
                        metric_name,
                        formula,
                        metric.get("description"),
                    ))

    if data_models:
        dest.insert_rows(SIGMA_DATA_MODEL, data_models)
    if elements:
        dest.insert_rows(SIGMA_ELEMENT, elements)
    if columns:
        dest.insert_rows(SIGMA_COLUMN, columns)
    if metrics:
        dest.insert_rows(SIGMA_METRIC, metrics)

    print(
        f"  sigma:    {len(data_models)} data models, {len(elements)} elements, "
        f"{len(columns)} columns, {len(metrics)} metrics"
    )


def _source_path(source: dict[str, Any] | None) -> str | None:
    if not isinstance(source, dict):
        return None
    path = source.get("path")
    if isinstance(path, list) and path:
        return ".".join(str(p) for p in path)
    return None


def _is_simple_metric(formula: str) -> bool:
    return bool(_SIMPLE_METRIC_RE.match(formula))


def _is_direct_formula(formula: str) -> bool:
    return bool(_FORMULA_COL_NAME_RE.match(formula))


def _col_display_name(col: dict) -> str | None:
    if name := col.get("name"):
        return name
    m = _FORMULA_COL_NAME_RE.match(col.get("formula") or "")
    return m.group(1) if m else None
