from __future__ import annotations

import unittest
import sys
from contextlib import contextmanager
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import patch

from agents_schema.agents_schema_writer import BigQueryAgentsSchemaWriter, DatabricksAgentsSchemaWriter
from agents_schema.dbt import DBT_MODEL


class BigQueryAgentsSchemaWriterTests(unittest.TestCase):
    def test_upsert_rows_loads_staging_and_merges(self):
        calls = []
        with _fake_bigquery_module():
            writer = BigQueryAgentsSchemaWriter(_FakeBigQueryClient(calls), "p")

            writer.upsert_rows(
                DBT_MODEL,
                [
                    ("model.pkg.orders", "orders", None, "analytics", "table", "", "models/orders.sql", [], "{}"),
                    (
                        "model.pkg.customers",
                        "customers",
                        None,
                        "analytics",
                        "view",
                        "desc",
                        "models/customers.sql",
                        ["mart"],
                        "{}",
                    ),
                ],
            )

        load_calls = [call for call in calls if call[0] == "load"]
        query_calls = [call for call in calls if call[0] == "query"]
        self.assertEqual(len(load_calls), 1)
        self.assertEqual(len(load_calls[0][1]), 2)
        self.assertEqual(len(query_calls), 1)
        query_sql = query_calls[0][1]
        self.assertIn("MERGE `p.agents.dbt_model` AS target", query_sql)
        self.assertIn("USING `p.agents._staging_dbt_model_", query_sql)
        self.assertIn("WHEN MATCHED THEN UPDATE SET", query_sql)
        self.assertIn("WHEN NOT MATCHED THEN INSERT", query_sql)
        self.assertTrue(any(call[0] == "delete_table" and call[1].startswith("p.agents._staging_dbt_model_") for call in calls))

    def test_reconcile_rows_deletes_stale_rows(self):
        calls = []
        with _fake_bigquery_module():
            writer = BigQueryAgentsSchemaWriter(_FakeBigQueryClient(calls), "p")

            writer.reconcile_rows(
                DBT_MODEL,
                [("model.pkg.orders", "orders", None, "analytics", "table", "", "models/orders.sql", [], "{}")],
            )

        query_sql = next(call[1] for call in calls if call[0] == "query")
        self.assertIn("MERGE `p.agents.dbt_model` AS target", query_sql)
        self.assertIn("WHEN NOT MATCHED BY SOURCE THEN DELETE", query_sql)

    def test_reconcile_rows_deletes_all_when_empty(self):
        calls = []
        with _fake_bigquery_module():
            writer = BigQueryAgentsSchemaWriter(_FakeBigQueryClient(calls), "p")

            writer.reconcile_rows(DBT_MODEL, [])

        self.assertIn(("query", "DELETE FROM `p.agents.dbt_model` WHERE TRUE", None), calls)

    def test_array_columns_are_repeated_string_fields(self):
        calls = []
        with _fake_bigquery_module():
            writer = BigQueryAgentsSchemaWriter(_FakeBigQueryClient(calls), "p", location="US")

            writer.ensure_table(DBT_MODEL)

        create_table_call = next(call for call in calls if call[0] == "create_table")
        table = create_table_call[1]
        tag_field = next(field for field in table.schema if field.args[0] == "tags")
        self.assertEqual(tag_field.args, ("tags", "STRING"))
        self.assertEqual(tag_field.kwargs["mode"], "REPEATED")
        create_dataset_call = next(call for call in calls if call[0] == "create_dataset")
        self.assertEqual(create_dataset_call[1].location, "US")


class DatabricksAgentsSchemaWriterTests(unittest.TestCase):
    def test_upsert_rows_uses_merge_and_native_markers(self):
        calls = []
        writer = DatabricksAgentsSchemaWriter(_fake_connection(calls))

        writer.upsert_rows(
            DBT_MODEL,
            [
                ("model.pkg.orders", "orders", None, "analytics", "table", "", "models/orders.sql", [], "{}"),
                ("model.pkg.customers", "customers", None, "analytics", "view", "desc", "models/customers.sql", ["mart"], "{}"),
            ],
        )

        merge_calls = [call for call in calls if call[0].startswith("MERGE")]
        self.assertEqual(len(merge_calls), 1)
        merge_sql, params = merge_calls[0]
        self.assertIn("MERGE INTO `agents`.`dbt_model` AS target", merge_sql)
        self.assertEqual(merge_sql.count("SELECT ? AS"), 2)
        self.assertIn("from_json(?, 'array<string>') AS `tags`", merge_sql)
        self.assertIn("target.`unique_id` = source.`unique_id`", merge_sql)
        self.assertIn("WHEN MATCHED THEN UPDATE SET", merge_sql)
        self.assertNotIn("%s", merge_sql)
        self.assertEqual(
            params,
            [
                "model.pkg.orders",
                "orders",
                None,
                "analytics",
                "table",
                "",
                "models/orders.sql",
                "[]",
                "{}",
                "model.pkg.customers",
                "customers",
                None,
                "analytics",
                "view",
                "desc",
                "models/customers.sql",
                '["mart"]',
                "{}",
            ],
        )

    def test_insert_rows_batches_json_arrays(self):
        calls = []
        writer = DatabricksAgentsSchemaWriter(_fake_connection(calls))

        writer.insert_rows(
            DBT_MODEL,
            [("model.pkg.orders", "orders", None, "analytics", "table", "", "models/orders.sql", ["finance"], "{}")],
        )

        self.assertEqual(len(calls), 1)
        insert_sql, params = calls[0]
        self.assertIn("INSERT INTO `agents`.`dbt_model`", insert_sql)
        self.assertIn("from_json(?, 'array<string>')", insert_sql)
        self.assertEqual(params[-1], '{}')

    def test_reconcile_rows_deletes_absent_primary_keys(self):
        calls = []
        writer = DatabricksAgentsSchemaWriter(_fake_connection(calls))

        writer.reconcile_rows(
            DBT_MODEL,
            [("model.pkg.orders", "orders", None, "analytics", "table", "", "models/orders.sql", [], "{}")],
        )

        delete_calls = [call for call in calls if call[0].startswith("DELETE FROM")]
        self.assertEqual(len(delete_calls), 1)
        delete_sql, params = delete_calls[0]
        self.assertIn("DELETE FROM `agents`.`dbt_model` AS target", delete_sql)
        self.assertIn("target.`unique_id` = source.`unique_id`", delete_sql)
        self.assertEqual(params, ["model.pkg.orders"])


def _fake_connection(calls):
    class FakeCursor:
        def execute(self, sql, params=None):
            calls.append((sql, params))

    @contextmanager
    def fake_cursor():
        yield FakeCursor()

    return SimpleNamespace(cursor=fake_cursor, close=lambda: None)


class _Job:
    def result(self):
        return None


class _FakeBigQueryClient:
    def __init__(self, calls):
        self.calls = calls

    def create_dataset(self, dataset, exists_ok=False):
        self.calls.append(("create_dataset", dataset, exists_ok))

    def create_table(self, table, exists_ok=False):
        self.calls.append(("create_table", table, exists_ok))

    def delete_table(self, table_ref, not_found_ok=False):
        self.calls.append(("delete_table", table_ref, not_found_ok))

    def load_table_from_json(self, rows, table_ref, job_config=None):
        self.calls.append(("load", rows, table_ref, job_config))
        return _Job()

    def query(self, sql, job_config=None):
        self.calls.append(("query", sql, job_config))
        return _Job()


def _fake_bigquery_module():
    fake_google = ModuleType("google")
    fake_cloud = ModuleType("google.cloud")
    fake_bigquery = ModuleType("google.cloud.bigquery")

    class WriteDisposition:
        WRITE_APPEND = "WRITE_APPEND"
        WRITE_TRUNCATE = "WRITE_TRUNCATE"

    class LoadJobConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class QueryJobConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class ScalarQueryParameter:
        def __init__(self, *args):
            self.args = args

    class SchemaField:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class Dataset:
        def __init__(self, ref):
            self.ref = ref
            self.location = None

    class Table:
        def __init__(self, ref, schema=None):
            self.ref = ref
            self.schema = schema

    fake_bigquery.WriteDisposition = WriteDisposition
    fake_bigquery.LoadJobConfig = LoadJobConfig
    fake_bigquery.QueryJobConfig = QueryJobConfig
    fake_bigquery.ScalarQueryParameter = ScalarQueryParameter
    fake_bigquery.SchemaField = SchemaField
    fake_bigquery.Dataset = Dataset
    fake_bigquery.Table = Table
    fake_cloud.bigquery = fake_bigquery
    fake_google.cloud = fake_cloud
    return patch.dict(
        sys.modules,
        {
            "google": fake_google,
            "google.cloud": fake_cloud,
            "google.cloud.bigquery": fake_bigquery,
        },
    )


if __name__ == "__main__":
    unittest.main()
