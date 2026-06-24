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
    "omni": (
        ("overview", "# Omni\nSemantic metadata parsed from Omni YAML files."),
        ("view", "One row per Omni view. See AGENTS.OMNI_VIEW."),
        ("dimension", "One row per Omni dimension. See AGENTS.OMNI_DIMENSION."),
        ("measure", "One row per Omni measure. See AGENTS.OMNI_MEASURE."),
        ("topic", "One row per Omni topic. See AGENTS.OMNI_TOPIC."),
        ("topic_join", "One row per join edge within a topic. See AGENTS.OMNI_TOPIC_JOIN."),
    ),
    "osi": (
        ("overview", "# OSI\nOpen Semantic Interchange metadata parsed from *.osi.yaml files."),
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
}


def upsert_provider_root(dest: Destination, provider: str) -> None:
    rows = [(provider, key, content) for key, content in ROOT_ENTRIES[provider]]
    dest.upsert_rows(ROOT, rows)
