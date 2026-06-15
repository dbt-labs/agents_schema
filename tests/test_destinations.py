import unittest
from unittest.mock import patch

from agents_schema.destinations import (
    DATABRICKS,
    Column,
    DatabricksDestination,
    SnowflakeDestination,
    TableSchema,
    _create_table_if_not_exists_sql,
    _delete_sql,
    _merge_sql,
)
from agents_schema.root import ROOT


class DestinationSqlTests(unittest.TestCase):
    def test_snowflake_destination_accepts_explicit_connection_kwargs(self):
        with patch("snowflake.connector.connect") as connect:
            dest = SnowflakeDestination(connect_kwargs={"account": "acct", "user": "user"})

        connect.assert_called_once_with(account="acct", user="user")
        dest.close()

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


ARRAY_TABLE = TableSchema(
    "items",
    (
        Column("id", "varchar", nullable=False),
        Column("tags", "array"),
    ),
    primary_key=("id",),
)


class DatabricksSqlTests(unittest.TestCase):
    def test_databricks_destination_accepts_explicit_connection_kwargs(self):
        with patch("databricks.sql.connect") as connect:
            dest = DatabricksDestination(
                connect_kwargs={"server_hostname": "h", "http_path": "p", "access_token": "t"}
            )

        connect.assert_called_once_with(server_hostname="h", http_path="p", access_token="t")
        dest.close()

    def test_create_table_maps_types_and_omits_primary_key(self):
        sql = _create_table_if_not_exists_sql(ROOT, "agents", DATABRICKS)

        self.assertEqual(
            sql,
            "CREATE TABLE IF NOT EXISTS agents.root (\n"
            "    provider STRING NOT NULL,\n"
            "    key STRING NOT NULL,\n"
            "    content STRING NOT NULL\n"
            ")",
        )

    def test_array_column_stored_as_string_without_parse_json(self):
        sql = _create_table_if_not_exists_sql(ARRAY_TABLE, "agents", DATABRICKS)

        self.assertIn("tags STRING", sql)
        self.assertNotIn("VARIANT", sql)
        merge = _merge_sql(ARRAY_TABLE, "agents", 1, DATABRICKS)
        self.assertNotIn("PARSE_JSON", merge)
        self.assertIn("%s AS tags", merge)

    def test_delete_uses_merge_when_matched_then_delete(self):
        sql = _delete_sql(ROOT, "agents", ("provider", "key"), 2, DATABRICKS)

        self.assertIn("MERGE INTO agents.root AS target", sql)
        self.assertIn("ON target.provider = source.provider AND target.key = source.key", sql)
        self.assertIn("WHEN MATCHED THEN DELETE", sql)
        self.assertFalse(sql.startswith("DELETE FROM"))


if __name__ == "__main__":
    unittest.main()
