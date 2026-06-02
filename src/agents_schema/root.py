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
    "tableau": (
        ("overview", "# Tableau\nMetadata parsed from Tableau Metadata API exports."),
        ("workbook", "One row per Tableau workbook. See AGENTS.TABLEAU_WORKBOOK."),
        ("datasource", "One row per Tableau datasource. See AGENTS.TABLEAU_DATASOURCE."),
        ("field", "One row per Tableau datasource field. See AGENTS.TABLEAU_FIELD."),
        ("dashboard", "One row per Tableau dashboard. See AGENTS.TABLEAU_DASHBOARD."),
        ("lineage", "Tableau datasource-to-workbook lineage edges. See AGENTS.TABLEAU_LINEAGE."),
    ),
    "dbt_semantic": (
        ("overview", "# dbt Semantic Layer\nMetricFlow semantic metadata parsed from semantic manifest exports."),
        ("semantic_model", "One row per dbt semantic model. See AGENTS.DBT_SEMANTIC_MODEL."),
        ("entity", "One row per dbt semantic model entity. See AGENTS.DBT_SEMANTIC_ENTITY."),
        ("dimension", "One row per dbt semantic model dimension. See AGENTS.DBT_SEMANTIC_DIMENSION."),
        ("measure", "One row per dbt semantic model measure. See AGENTS.DBT_SEMANTIC_MEASURE."),
        ("metric", "One row per dbt Semantic Layer metric. See AGENTS.DBT_SEMANTIC_METRIC."),
    ),
    "datahub": (
        ("overview", "# DataHub\nCatalog metadata parsed from DataHub entity exports."),
        ("entity", "One row per DataHub entity. See AGENTS.DATAHUB_ENTITY."),
        ("field", "One row per schema field. See AGENTS.DATAHUB_FIELD."),
        ("owner", "One row per DataHub ownership assignment. See AGENTS.DATAHUB_OWNER."),
        ("lineage", "One row per DataHub upstream lineage edge. See AGENTS.DATAHUB_LINEAGE."),
    ),
    "openmetadata": (
        ("overview", "# OpenMetadata\nCatalog metadata parsed from OpenMetadata API exports."),
        ("entity", "One row per OpenMetadata entity. See AGENTS.OPENMETADATA_ENTITY."),
        ("field", "One row per OpenMetadata field or column. See AGENTS.OPENMETADATA_FIELD."),
        ("lineage", "One row per OpenMetadata lineage edge. See AGENTS.OPENMETADATA_LINEAGE."),
    ),
    "atlan": (
        ("overview", "# Atlan\nCatalog metadata parsed from Atlan asset exports."),
        ("asset", "One row per Atlan asset. See AGENTS.ATLAN_ASSET."),
        ("field", "One row per Atlan column or field asset. See AGENTS.ATLAN_FIELD."),
        ("lineage", "One row per Atlan lineage edge. See AGENTS.ATLAN_LINEAGE."),
    ),
    "alation": (
        ("overview", "# Alation\nCatalog metadata parsed from Alation API exports."),
        ("data_source", "One row per Alation data source. See AGENTS.ALATION_DATA_SOURCE."),
        ("table", "One row per Alation table. See AGENTS.ALATION_TABLE."),
        ("column", "One row per Alation column. See AGENTS.ALATION_COLUMN."),
        ("glossary_term", "One row per Alation glossary term. See AGENTS.ALATION_GLOSSARY_TERM."),
    ),
    "collibra": (
        ("overview", "# Collibra\nGovernance metadata parsed from Collibra API exports."),
        ("asset", "One row per Collibra asset. See AGENTS.COLLIBRA_ASSET."),
        ("attribute", "One row per Collibra asset attribute. See AGENTS.COLLIBRA_ATTRIBUTE."),
        ("relation", "One row per Collibra asset relation. See AGENTS.COLLIBRA_RELATION."),
        ("responsibility", "One row per Collibra responsibility. See AGENTS.COLLIBRA_RESPONSIBILITY."),
    ),
    "metabase": (
        ("overview", "# Metabase\nBI metadata parsed from Metabase API exports."),
        ("database", "One row per Metabase database. See AGENTS.METABASE_DATABASE."),
        ("table", "One row per Metabase table. See AGENTS.METABASE_TABLE."),
        ("field", "One row per Metabase field. See AGENTS.METABASE_FIELD."),
        ("card", "One row per Metabase question/card. See AGENTS.METABASE_CARD."),
        ("dashboard", "One row per Metabase dashboard. See AGENTS.METABASE_DASHBOARD."),
    ),
    "cube": (
        ("overview", "# Cube\nSemantic metadata parsed from Cube /v1/meta exports."),
        ("cube", "One row per Cube cube. See AGENTS.CUBE_CUBE."),
        ("measure", "One row per Cube measure. See AGENTS.CUBE_MEASURE."),
        ("dimension", "One row per Cube dimension. See AGENTS.CUBE_DIMENSION."),
        ("segment", "One row per Cube segment. See AGENTS.CUBE_SEGMENT."),
        ("join", "One row per Cube join. See AGENTS.CUBE_JOIN."),
    ),
}


def upsert_provider_root(dest: Destination, provider: str) -> None:
    rows = [(provider, key, content) for key, content in ROOT_ENTRIES[provider]]
    dest.upsert_rows(ROOT, rows)
