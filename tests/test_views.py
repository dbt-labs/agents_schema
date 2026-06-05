import unittest

from agents_schema.views import BUILT_IN_PROVIDER_VIEW_NAMES, CORE_VIEW_NAMES, build_context_view_sql


class ContextViewSqlTests(unittest.TestCase):
    def test_builds_only_information_schema_surfaces(self):
        views = build_context_view_sql({"dbt_model", "dbt_column"})

        self.assertEqual(BUILT_IN_PROVIDER_VIEW_NAMES | CORE_VIEW_NAMES, set(views))
        self.assertEqual(CORE_VIEW_NAMES, {"schemata", "tables", "columns"})
        # relationships / metrics / entities are out of scope for v1
        self.assertNotIn("relationships", views)
        self.assertNotIn("metrics", views)
        self.assertNotIn("entities", views)

    def test_builds_builtin_provider_views_from_raw_provider_tables(self):
        views = build_context_view_sql({"dbt_model", "dbt_column"})

        self.assertIn("FROM agents.dbt_model", views["dbt_tables"])
        self.assertIn("FROM agents.dbt_column c", views["dbt_columns"])
        self.assertIn("FROM agents.dbt_model", views["dbt_schemata"])

    def test_core_schemata_uses_information_schema_schemata_spine(self):
        views = build_context_view_sql({"dbt_model", "lookml_view", "osi_dataset"})
        schemata = views["schemata"]

        self.assertIn("SELECT\n  t.*", schemata)
        self.assertIn("FROM information_schema.schemata t", schemata)
        self.assertIn("dbt.display_name AS dbt_display_name", schemata)
        self.assertIn("lookml.source_object_id AS lookml_source_object_id", schemata)
        self.assertIn("FROM agents.dbt_schemata", schemata)
        self.assertIn("LOWER(t.schema_name) = LOWER(dbt.schema_name)", schemata)
        self.assertIn("GROUP BY catalog_name, schema_name", schemata)

    def test_core_tables_uses_information_schema_star_spine(self):
        views = build_context_view_sql({"dbt_model", "lookml_view", "osi_dataset"})
        tables = views["tables"]

        # native spine is SELECT t.* — no hardcoded information_schema column list
        self.assertIn("SELECT\n  t.*", tables)
        self.assertIn("FROM information_schema.tables t", tables)
        self.assertNotIn("t.is_hybrid", tables)
        self.assertNotIn("t.last_ddl", tables)

    def test_core_tables_merges_all_provider_relations_by_identity(self):
        views = build_context_view_sql({"dbt_model", "lookml_view", "osi_dataset"})
        tables = views["tables"]

        # one prefixed enrichment column per provider, joined by identity
        self.assertIn("dbt.description AS dbt_description", tables)
        self.assertIn("lookml.ai_context AS lookml_ai_context", tables)
        self.assertIn("osi.description AS osi_description", tables)
        self.assertIn("FROM agents.dbt_tables", tables)
        self.assertIn("FROM agents.osi_tables", tables)
        self.assertIn("LOWER(t.table_name) = LOWER(dbt.table_name)", tables)
        self.assertIn("GROUP BY table_catalog, table_schema, table_name", tables)
        # generic merge: no provider-specific convenience columns
        self.assertNotIn("custom_count", tables)
        self.assertNotIn("custom_summary", tables)

    def test_core_columns_merges_by_column_identity(self):
        views = build_context_view_sql({"dbt_model", "dbt_column"})
        columns = views["columns"]

        self.assertIn("SELECT\n  t.*", columns)
        self.assertIn("FROM information_schema.columns t", columns)
        self.assertIn("FROM agents.dbt_columns", columns)
        self.assertIn("LOWER(t.column_name) = LOWER(dbt.column_name)", columns)
        self.assertIn("dbt.description AS dbt_description", columns)

    def test_core_tables_merges_external_provider_relation_by_suffix(self):
        views = build_context_view_sql({"notes_on_tables"})

        self.assertNotIn("notes_on_tables", views)
        self.assertIn("notes_on.table_type AS notes_on_table_type", views["tables"])
        self.assertIn("FROM agents.notes_on_tables", views["tables"])
        self.assertIn("LOWER(t.table_name) = LOWER(notes_on.table_name)", views["tables"])

    def test_dbt_relationships_view_is_gone(self):
        views = build_context_view_sql({"dbt_model", "dbt_dependency"})

        self.assertNotIn("dbt_relationships", views)

    def test_osi_columns_parse_source_table_like_osi_tables(self):
        views = build_context_view_sql({"osi_dataset", "osi_field"})

        # columns identity must align with tables identity (parse source_table)
        self.assertIn("THEN SPLIT_PART(d.source_table, '.', 2)", views["osi_columns"])
        self.assertIn("END AS table_schema", views["osi_columns"])
        self.assertIn("END AS table_name", views["osi_columns"])

    def test_lookml_tables_parse_simple_sql_table_name(self):
        views = build_context_view_sql({"lookml_view"})

        self.assertIn("REGEXP_COUNT(sql_table_name, '[.]') = 2", views["lookml_tables"])
        self.assertIn("THEN SPLIT_PART(sql_table_name, '.', 1)", views["lookml_tables"])
        self.assertIn("END AS table_catalog", views["lookml_tables"])

    def test_lookml_columns_use_same_sql_table_name_identity_as_tables(self):
        views = build_context_view_sql({"lookml_view", "lookml_dimension"})

        self.assertIn("FROM agents.lookml_dimension d", views["lookml_columns"])
        self.assertIn("JOIN agents.lookml_view v ON v.name = d.view_name", views["lookml_columns"])
        self.assertIn("REGEXP_COUNT(v.sql_table_name, '[.]') = 2", views["lookml_columns"])
        self.assertIn("ELSE v.name", views["lookml_columns"])

    def test_missing_provider_relations_become_typed_empty_views(self):
        views = build_context_view_sql(set())

        # no provider relations exist: built-in provider views are empty typed projections,
        # but AGENTS.SCHEMATA/TABLES still work as information_schema passthroughs
        self.assertIn("WHERE 1 = 0", views["dbt_tables"])
        self.assertIn("CAST(NULL AS VARCHAR) AS catalog_name", views["dbt_schemata"])
        self.assertIn("FROM information_schema.schemata t", views["schemata"])
        self.assertIn("FROM information_schema.tables t", views["tables"])


if __name__ == "__main__":
    unittest.main()
