import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agents_schema.destinations import Column, TableSchema, _create_table_if_not_exists_sql, _merge_sql, open_destination
from agents_schema.root import ROOT


class DestinationSqlTests(unittest.TestCase):
    def test_root_create_table_uses_if_not_exists(self):
        sql = _create_table_if_not_exists_sql(ROOT, "agents")

        self.assertEqual(
            sql,
            "CREATE TABLE IF NOT EXISTS agents.root (\n"
            "    provider VARCHAR NOT NULL,\n"
            "    key VARCHAR NOT NULL,\n"
            "    content TEXT NOT NULL,\n"
            "    PRIMARY KEY (provider, key)\n"
            ")",
        )

    def test_root_merge_upserts_on_provider_and_key(self):
        sql = _merge_sql(ROOT, "agents", 2)

        self.assertIn("MERGE INTO agents.root AS target", sql)
        self.assertIn(
            "USING (SELECT %s AS provider, %s AS key, %s AS content "
            "UNION ALL SELECT %s AS provider, %s AS key, %s AS content) AS source",
            sql,
        )
        self.assertIn("ON target.provider = source.provider AND target.key = source.key", sql)
        self.assertIn("WHEN MATCHED THEN UPDATE SET target.content = source.content", sql)
        self.assertIn(
            "WHEN NOT MATCHED THEN INSERT (provider, key, content) "
            "VALUES (source.provider, source.key, source.content)",
            sql,
        )

    def test_duckdb_destination_writes_tables_and_upserts_root(self):
        table = TableSchema(
            "agents.local_test",
            (
                Column("id", "varchar", nullable=False),
                Column("tags", "array"),
            ),
            primary_key=("id",),
        )

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "agents.duckdb"
            credentials = f'{{"type": "duckdb", "path": "{path}"}}'
            with patch.dict("os.environ", {"WAREHOUSE_CREDENTIALS": credentials}):
                with open_destination({"warehouse": {"type": "duckdb"}}) as dest:
                    dest.upsert_rows(ROOT, [("powerbi", "overview", "Power BI docs")])
                    dest.upsert_rows(ROOT, [("powerbi", "overview", "Updated Power BI docs")])
                    dest.replace_table(table)
                    dest.insert_rows(table, [("row_1", ["a", "b"])])

            import duckdb

            con = duckdb.connect(str(path))
            try:
                catalog = con.execute("SELECT current_database()").fetchone()[0]
                root_rows = con.execute(
                    f'SELECT provider, key, content FROM "{catalog}"."agents"."root" WHERE provider = \'powerbi\''
                ).fetchall()
                test_rows = con.execute(
                    f'SELECT id, CAST(tags AS VARCHAR) FROM "{catalog}"."agents"."local_test"'
                ).fetchall()
            finally:
                con.close()

        self.assertEqual(root_rows, [("powerbi", "overview", "Updated Power BI docs")])
        self.assertEqual(test_rows, [("row_1", '["a", "b"]')])


if __name__ == "__main__":
    unittest.main()
