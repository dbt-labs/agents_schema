"""Snowflake semantic view connector: writes pointers into AGENTS.ROOT."""
from __future__ import annotations

from collections.abc import Iterable

from .config import ConfigError
from .destinations import Destination, open_destination
from .root import ROOT

__all__ = ["publish_semantic_view_pointers", "run"]

PROVIDER = "snowflake_semantic"
KEY_PREFIX = "semantic_view/"


def run(cfg: dict) -> None:
    semantic_views = _semantic_views_from_config(cfg)
    with open_destination(cfg) as dest:
        publish_semantic_view_pointers(dest, semantic_views)


def publish_semantic_view_pointers(dest: Destination, semantic_views: Iterable[str]) -> None:
    rows = [_root_row(name) for name in _normalize_semantic_views(semantic_views)]
    dest.upsert_rows(ROOT, rows)
    print(f"  snowflake-semantic: {len(rows)} semantic views")


def _semantic_views_from_config(cfg: dict) -> list[str]:
    return list(cfg.get("metadata_connection", {}).get("semantic_views", []))


def _normalize_semantic_views(semantic_views: Iterable[str]) -> list[str]:
    names = []
    seen = set()
    for semantic_view in semantic_views:
        name = semantic_view.strip()
        if not name:
            raise ConfigError("semantic view names must not be empty")
        if name not in seen:
            names.append(name)
            seen.add(name)
    if not names:
        raise ConfigError("at least one semantic view is required")
    return names


def _root_row(semantic_view: str) -> tuple[str, str, str]:
    return (
        PROVIDER,
        f"{KEY_PREFIX}{semantic_view}",
        (
            "# Snowflake Semantic View\n\n"
            f"Snowflake object: `{semantic_view}`\n\n"
            "This row is a pointer to a native Snowflake semantic view. "
            "The semantic definition lives in Snowflake. "
            "Inspect the Snowflake object for current "
            "dimensions, metrics, relationships, and query behavior."
        ),
    )
