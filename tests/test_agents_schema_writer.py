from __future__ import annotations

import unittest
from contextlib import contextmanager
from types import SimpleNamespace

from agents_schema.agents_schema_writer import DatabricksAgentsSchemaWriter
from agents_schema.dbt import DBT_MODEL


class DatabricksAgentsSchemaWriterTests(unittest.TestCase):
    def test_upsert_rows_uses_merge_and_native_markers(self):
        calls = []
        writer = DatabricksAgentsSchemaWriter(_fake_connection(calls))

        writer.upsert_rows(
            DBT_MODEL,
            [
                ("model.pkg.orders", "orders", "analytics", "table", "", "models/orders.sql", []),
                ("model.pkg.customers", "customers", "analytics", "view", "desc", "models/customers.sql", ["mart"]),
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
                "analytics",
                "table",
                "",
                "models/orders.sql",
                "[]",
                "model.pkg.customers",
                "customers",
                "analytics",
                "view",
                "desc",
                "models/customers.sql",
                '["mart"]',
            ],
        )

    def test_insert_rows_batches_json_arrays(self):
        calls = []
        writer = DatabricksAgentsSchemaWriter(_fake_connection(calls))

        writer.insert_rows(
            DBT_MODEL,
            [("model.pkg.orders", "orders", "analytics", "table", "", "models/orders.sql", ["finance"])],
        )

        self.assertEqual(len(calls), 1)
        insert_sql, params = calls[0]
        self.assertIn("INSERT INTO `agents`.`dbt_model`", insert_sql)
        self.assertIn("from_json(?, 'array<string>')", insert_sql)
        self.assertEqual(params[-1], '["finance"]')

    def test_reconcile_rows_deletes_absent_primary_keys(self):
        calls = []
        writer = DatabricksAgentsSchemaWriter(_fake_connection(calls))

        writer.reconcile_rows(
            DBT_MODEL,
            [("model.pkg.orders", "orders", "analytics", "table", "", "models/orders.sql", [])],
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


if __name__ == "__main__":
    unittest.main()
