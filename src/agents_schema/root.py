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
        ("overview", "# OSI\nOpen Semantic Interchange metadata parsed from *.osi.yaml files."),
        ("dataset", "One row per OSI dataset. See AGENTS.OSI_DATASET."),
        ("field", "One row per OSI dataset field. See AGENTS.OSI_FIELD."),
        ("metric", "One row per OSI metric. See AGENTS.OSI_METRIC."),
        ("relationship", "One row per OSI relationship. See AGENTS.OSI_RELATIONSHIP."),
    ),
    "powerbi": (
        ("overview", "# Power BI\nMetadata parsed from Microsoft Fabric / Power BI scanner exports."),
        ("workspace", "One row per Power BI workspace. See AGENTS.POWERBI_WORKSPACE."),
        ("semantic_model", "One row per Power BI semantic model or dataset. See AGENTS.POWERBI_SEMANTIC_MODEL."),
        ("measure", "One row per Power BI model measure. See AGENTS.POWERBI_MEASURE."),
        ("report", "One row per Power BI report. See AGENTS.POWERBI_REPORT."),
        ("lineage", "Power BI model-to-report and scanner lineage edges. See AGENTS.POWERBI_LINEAGE."),
    ),
}


def upsert_provider_root(dest: Destination, provider: str) -> None:
    rows = [(provider, key, content) for key, content in ROOT_ENTRIES[provider]]
    dest.upsert_rows(ROOT, rows)
