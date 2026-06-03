"""Power BI connector: writes agents.powerbi* from metadata exports."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .config import ConfigError
from .destinations import Column, Destination, TableSchema, open_destination
from .root import upsert_provider_root

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

POWERBI_TABLES = (
    POWERBI_WORKSPACE,
    POWERBI_SEMANTIC_MODEL,
    POWERBI_TABLE,
    POWERBI_COLUMN,
    POWERBI_MEASURE,
    POWERBI_REPORT,
    POWERBI_LINEAGE,
)
SUPPORTED_METADATA_SUFFIXES = {".json", ".yaml", ".yml"}


def run(cfg: dict[str, Any]) -> None:
    metadata_path = Path(cfg["metadata_connection"]["path"])
    documents = _load_metadata_documents(metadata_path)
    rows_by_table = _powerbi_parse(documents)

    with open_destination(cfg) as dest:
        upsert_provider_root(dest, "powerbi")
        _create_tables(dest)
        _ingest_rows(dest, rows_by_table)

    print(
        f"  powerbi: {len(rows_by_table[POWERBI_SEMANTIC_MODEL])} models, "
        f"{len(rows_by_table[POWERBI_MEASURE])} measures, "
        f"{len(rows_by_table[POWERBI_REPORT])} reports"
    )


def _load_metadata_documents(path: Path) -> list[Any]:
    if path.is_file():
        return [_load_metadata_file(path)]
    if not path.exists():
        raise FileNotFoundError(f"metadata path not found: {path}")
    if not path.is_dir():
        raise ConfigError(f"metadata path must be a file or directory: {path}")

    files = sorted(p for p in path.rglob("*") if p.suffix.lower() in SUPPORTED_METADATA_SUFFIXES)
    if not files:
        suffixes = ", ".join(sorted(SUPPORTED_METADATA_SUFFIXES))
        raise FileNotFoundError(f"no metadata export files ({suffixes}) found in {path}")
    return [_load_metadata_file(file_path) for file_path in files]


def _load_metadata_file(path: Path) -> Any:
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError as e:
            raise ConfigError(f"{path} is not valid JSON: {e}") from e
    if suffix in {".yaml", ".yml"}:
        try:
            return yaml.safe_load(path.read_text())
        except yaml.YAMLError as e:
            raise ConfigError(f"{path} is not valid YAML: {e}") from e
    raise ConfigError(f"unsupported metadata file type for {path}")


def _create_tables(dest: Destination) -> None:
    for table in POWERBI_TABLES:
        dest.replace_table(table)


def _ingest_rows(dest: Destination, rows_by_table: dict[TableSchema, list[tuple[Any, ...]]]) -> None:
    for table, rows in rows_by_table.items():
        if rows:
            dest.insert_rows(table, rows)


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


def _powerbi_parse(documents: list[Any]) -> dict[TableSchema, list[tuple[Any, ...]]]:
    rows = {table: [] for table in POWERBI_TABLES}
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
