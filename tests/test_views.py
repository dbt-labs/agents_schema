import unittest

from agents_schema.views import CORE_VIEW_NAMES, PROVIDER_VIEW_NAMES, build_context_view_sql


class ContextViewSqlTests(unittest.TestCase):
    def test_builds_provider_views_from_raw_provider_tables(self):
        views = build_context_view_sql({"dbt_model", "dbt_column"})

        self.assertEqual(PROVIDER_VIEW_NAMES | CORE_VIEW_NAMES, set(views))
        self.assertIn("FROM agents.dbt_model", views["dbt_tables"])
        self.assertIn("FROM agents.dbt_column c", views["dbt_columns"])

    def test_core_tables_enriches_information_schema_with_provider_tables(self):
        views = build_context_view_sql({"dbt_model", "dbt_column", "lookml_view"})

        self.assertIn("FROM information_schema.tables t", views["tables"])
        self.assertIn("FROM agents.dbt_tables", views["tables"])
        self.assertIn(") dbt", views["tables"])
        self.assertIn("FROM agents.lookml_tables", views["tables"])
        self.assertIn(") lookml", views["tables"])
        self.assertIn("dbt.description AS dbt_description", views["tables"])
        self.assertIn("lookml.ai_context AS lookml_ai_context", views["tables"])
        self.assertIn("LOWER(t.table_name) = LOWER(dbt.table_name)", views["tables"])
        self.assertIn("GROUP BY table_catalog, table_schema, table_name", views["tables"])
        self.assertIn("SUM(memories_count) AS memories_count", views["tables"])
        self.assertIn("t.last_ddl", views["tables"])
        self.assertIn("t.last_ddl_by", views["tables"])
        self.assertIn("t.auto_clustering_on", views["tables"])
        self.assertIn("t.is_hybrid", views["tables"])
        self.assertNotIn("FROM agents.dbt_model", views["tables"])

    def test_core_columns_still_union_provider_normalized_columns(self):
        views = build_context_view_sql({"dbt_model", "dbt_column", "lookml_view"})

        self.assertIn("FROM agents.dbt_columns", views["columns"])
        self.assertNotIn("FROM agents.dbt_column c", views["columns"])

    def test_builds_metric_view_from_provider_metric_views(self):
        views = build_context_view_sql({"lookml_measure", "osi_metric"})

        self.assertIn("FROM agents.lookml_metrics", views["metrics"])
        self.assertIn("FROM agents.osi_metrics", views["metrics"])
        self.assertIn("FROM agents.lookml_measure", views["lookml_metrics"])
        self.assertIn("FROM agents.osi_metric", views["osi_metrics"])

    def test_dbt_relationships_use_model_names_for_table_endpoints(self):
        views = build_context_view_sql({"dbt_model", "dbt_dependency"})

        self.assertIn("JOIN agents.dbt_model upstream ON upstream.unique_id = d.upstream_id", views["dbt_relationships"])
        self.assertIn("JOIN agents.dbt_model downstream ON downstream.unique_id = d.downstream_id", views["dbt_relationships"])
        self.assertIn("upstream.name AS from_table", views["dbt_relationships"])
        self.assertIn("downstream.name AS to_table", views["dbt_relationships"])

    def test_osi_relationships_use_dataset_source_tables_for_table_endpoints(self):
        views = build_context_view_sql({"osi_dataset", "osi_relationship"})

        self.assertIn("JOIN agents.osi_dataset from_dataset ON from_dataset.name = r.from_dataset", views["osi_relationships"])
        self.assertIn("JOIN agents.osi_dataset to_dataset ON to_dataset.name = r.to_dataset", views["osi_relationships"])
        self.assertIn("from_dataset.source_table AS from_table", views["osi_relationships"])
        self.assertIn("to_dataset.source_table AS to_table", views["osi_relationships"])

    def test_osi_tables_parse_source_table_for_table_merge_identity(self):
        views = build_context_view_sql({"osi_dataset"})

        self.assertIn("REGEXP_COUNT(source_table, '[.]') = 2", views["osi_tables"])
        self.assertIn("THEN SPLIT_PART(source_table, '.', 1)", views["osi_tables"])
        self.assertIn("END AS table_catalog", views["osi_tables"])
        self.assertIn("END AS table_schema", views["osi_tables"])
        self.assertIn("THEN SPLIT_PART(source_table, '.', 3)", views["osi_tables"])
        self.assertIn("END AS table_name", views["osi_tables"])

    def test_lookml_tables_parse_simple_sql_table_name(self):
        views = build_context_view_sql({"lookml_view"})

        self.assertIn("REGEXP_COUNT(sql_table_name, '[.]') = 2", views["lookml_tables"])
        self.assertIn("THEN SPLIT_PART(sql_table_name, '.', 1)", views["lookml_tables"])
        self.assertIn("END AS table_catalog", views["lookml_tables"])
        self.assertIn("END AS table_schema", views["lookml_tables"])
        self.assertIn("THEN SPLIT_PART(sql_table_name, '.', 3)", views["lookml_tables"])
        self.assertIn("END AS table_name", views["lookml_tables"])
        self.assertIn("ELSE name", views["lookml_tables"])

    def test_lookml_columns_use_same_sql_table_name_identity_as_tables(self):
        views = build_context_view_sql({"lookml_view", "lookml_dimension"})

        self.assertIn("FROM agents.lookml_dimension d", views["lookml_columns"])
        self.assertIn("JOIN agents.lookml_view v ON v.name = d.view_name", views["lookml_columns"])
        self.assertIn("REGEXP_COUNT(v.sql_table_name, '[.]') = 2", views["lookml_columns"])
        self.assertIn("THEN SPLIT_PART(v.sql_table_name, '.', 3)", views["lookml_columns"])
        self.assertIn("ELSE v.name", views["lookml_columns"])

    def test_empty_view_has_typed_projection(self):
        views = build_context_view_sql(set())

        self.assertIn("CAST(NULL AS VARCHAR) AS table_name", views["dbt_tables"])
        self.assertIn("WHERE 1 = 0", views["dbt_tables"])
        self.assertIn("FROM information_schema.tables t", views["tables"])
        self.assertIn("CAST(NULL AS VARCHAR) AS entity_id", views["entities"])


if __name__ == "__main__":
    unittest.main()
