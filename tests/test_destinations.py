import unittest
from unittest.mock import patch

from agents_schema.destinations import (
    DatabricksDestination,
    SnowflakeDestination,
    _create_table_if_not_exists_sql,
    _databricks_connect_kwargs_from_secret,
    _merge_sql,
    open_destination,
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

    def test_databricks_destination_accepts_explicit_connection_kwargs(self):
        with patch("databricks.sql.connect") as connect:
            dest = DatabricksDestination(
                connect_kwargs={
                    "server_hostname": "dbc-test.cloud.databricks.com",
                    "http_path": "/sql/1.0/warehouses/abc",
                    "catalog": "main",
                    "access_token": "tok",
                }
            )

        connect.assert_called_once_with(
            server_hostname="dbc-test.cloud.databricks.com",
            http_path="/sql/1.0/warehouses/abc",
            catalog="main",
            access_token="tok",
        )
        dest.close()

    def test_databricks_credentials_accept_public_shape(self):
        kwargs = _databricks_connect_kwargs_from_secret(
            {
                "type": "databricks",
                "host": "dbc-test.cloud.databricks.com",
                "http_path": "/sql/1.0/warehouses/abc",
                "catalog": "main",
                "token": "tok",
            }
        )

        self.assertEqual(
            kwargs,
            {
                "server_hostname": "dbc-test.cloud.databricks.com",
                "http_path": "/sql/1.0/warehouses/abc",
                "catalog": "main",
                "access_token": "tok",
            },
        )

    def test_databricks_credentials_accept_internal_aliases(self):
        kwargs = _databricks_connect_kwargs_from_secret(
            {
                "type": "databricks",
                "serverHostName": "dbc-test.cloud.databricks.com",
                "httpPath": "/sql/1.0/warehouses/abc",
                "catalog": "main",
                "personalAccessToken": "tok",
            }
        )

        self.assertEqual(kwargs["server_hostname"], "dbc-test.cloud.databricks.com")
        self.assertEqual(kwargs["http_path"], "/sql/1.0/warehouses/abc")
        self.assertEqual(kwargs["access_token"], "tok")

    def test_open_destination_supports_databricks(self):
        with patch("agents_schema.destinations.DatabricksDestination") as destination:
            result = open_destination({"warehouse": {"type": "databricks"}})

        self.assertIs(result, destination.return_value)


if __name__ == "__main__":
    unittest.main()
