import unittest
from unittest.mock import patch

from agents_schema.destinations import SnowflakeDestination, _create_table_if_not_exists_sql, _merge_sql
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


if __name__ == "__main__":
    unittest.main()
