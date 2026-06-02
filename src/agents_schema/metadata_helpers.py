"""Shared helpers for metadata export connectors."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from .destinations import Destination, TableSchema, open_destination
from .metadata_io import load_metadata_documents
from .root import upsert_provider_root


def run_connector(
    cfg: dict[str, Any],
    provider: str,
    tables: tuple[TableSchema, ...],
    parse: Callable[[list[Any]], dict[TableSchema, list[tuple[Any, ...]]]],
    summary: Callable[[dict[TableSchema, list[tuple[Any, ...]]]], str],
) -> None:
    metadata_path = Path(cfg["metadata_connection"]["path"])
    documents = load_metadata_documents(metadata_path)
    rows_by_table = parse(documents)

    with open_destination(cfg) as dest:
        upsert_provider_root(dest, provider)
        _create_tables(dest, tables)
        _ingest_rows(dest, rows_by_table)

    print(summary(rows_by_table))


def _create_tables(dest: Destination, tables: Iterable[TableSchema]) -> None:
    for table in tables:
        dest.replace_table(table)


def _ingest_rows(dest: Destination, rows_by_table: dict[TableSchema, list[tuple[Any, ...]]]) -> None:
    for table, rows in rows_by_table.items():
        if rows:
            dest.insert_rows(table, rows)


def _rows(tables: Iterable[TableSchema]) -> dict[TableSchema, list[tuple[Any, ...]]]:
    return {table: [] for table in tables}


def _summarize(provider: str, labels: tuple[tuple[TableSchema, str], ...]) -> Callable[[dict[TableSchema, list[tuple[Any, ...]]]], str]:
    def summary(rows_by_table: dict[TableSchema, list[tuple[Any, ...]]]) -> str:
        parts = [f"{len(rows_by_table.get(table, []))} {label}" for table, label in labels]
        return f"  {provider:<9}" + ", ".join(parts)

    return summary


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


def _nested(obj: dict[str, Any], *path: str) -> Any:
    value: Any = obj
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


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


def _owner_name(obj: dict[str, Any]) -> str | None:
    owner = obj.get("owner")
    if isinstance(owner, dict):
        return _name(owner) or _text(_pick(owner, "id", "urn"))
    return _text(owner)


def _platform(obj: dict[str, Any]) -> str | None:
    platform = obj.get("platform")
    if isinstance(platform, dict):
        return _text(_pick(platform, "name", "urn"))
    return _text(platform or obj.get("platformName"))
