"""Shared AGENTS.ROOT provider registry."""
from __future__ import annotations

from .destinations import Column, Destination, TableSchema

__all__ = ["ROOT", "upsert_provider_root"]

ROOT = TableSchema(
    "agents.root",
    (
        Column("provider", "varchar", nullable=False),
        Column("key", "varchar", nullable=False),
        Column("content", "text", nullable=False),
    ),
    primary_key=("provider", "key"),
)

ROOT_ENTRIES = {
    "dbt": (
        ("overview", "# dbt\nTransformation metadata from dbt manifest.json."),
        ("model", "One row per dbt model. See AGENTS.DBT_MODEL."),
        ("column", "One row per documented dbt model column. See AGENTS.DBT_COLUMN."),
        ("dependency", "Direct dbt DAG edges. See AGENTS.DBT_DEPENDENCY."),
    ),
    "lookml": (
        ("overview", "# LookML\nSemantic metadata parsed from LookML files."),
        ("view", "One row per LookML view. See AGENTS.LOOKML_VIEW."),
        ("dimension", "One row per LookML dimension or dimension group. See AGENTS.LOOKML_DIMENSION."),
        ("measure", "One row per LookML measure. See AGENTS.LOOKML_MEASURE."),
        ("explore", "One row per LookML explore. See AGENTS.LOOKML_EXPLORE."),
    ),
    "osi": (
        ("overview", "# OSI\nOpen Semantic Interchange metadata parsed from *.osi.yaml files. The canonical semantic-layer source; other formats (e.g. LookML) reach AGENTS.OSI_* by being converted to OSI first."),
        ("model", "One row per OSI semantic model. See AGENTS.OSI_MODEL."),
        ("dataset", "One row per OSI dataset. See AGENTS.OSI_DATASET."),
        ("field", "One row per OSI dataset field. See AGENTS.OSI_FIELD."),
        ("metric", "One row per OSI metric. See AGENTS.OSI_METRIC."),
        ("relationship", "One row per OSI relationship. See AGENTS.OSI_RELATIONSHIP."),
    ),
    "skills": (
        ("overview", "# Skills\nWarehouse-delivered agent skills published as AGENTS.ROOT rows."),
        ("root-convention", "Skills are rows in AGENTS.ROOT where key starts with skill/."),
        ("skill_use", "Optional parsed skill data-use declarations. See AGENTS.SKILL_USE."),
    ),
    "snowflake_semantic": (
        ("overview", "# Snowflake Semantic\nPointer rows for native Snowflake semantic views. Each key semantic_view/<name> in AGENTS.ROOT points to one Snowflake semantic view object. Inspect the Snowflake object for current dimensions, metrics, relationships, and query behavior."),
    ),
}


def upsert_provider_root(dest: Destination, provider: str) -> None:
    rows = [(provider, key, content) for key, content in ROOT_ENTRIES[provider]]
    dest.upsert_rows(ROOT, rows)
