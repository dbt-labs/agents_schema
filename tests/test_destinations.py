import io
import unittest
import urllib.error
from unittest.mock import patch

from agents_schema.agents_schema_writer import AGENTS_SCHEMA
from agents_schema.config import ConfigError
from agents_schema.destinations import (
    BigQueryDestination,
    ClickHouseDestination,
    DatabricksDestination,
    SnowflakeDestination,
    _bigquery_credentials_from_secret,
    _clickhouse_connect_kwargs_from_secret,
    _create_table_if_not_exists_sql,
    _databricks_connect_kwargs_from_secret,
    _github_oidc_token,
    _merge_sql,
    _snowflake_connect_kwargs_from_secret,
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
        sql = _create_table_if_not_exists_sql(ROOT, AGENTS_SCHEMA)

        self.assertEqual(
            sql,
            "CREATE TABLE IF NOT EXISTS AGENTS.ROOT (\n"
            "    provider VARCHAR NOT NULL,\n"
            "    key VARCHAR NOT NULL,\n"
            "    content TEXT NOT NULL,\n"
            "    PRIMARY KEY (provider, key)\n"
            ")",
        )

    def test_root_merge_upserts_on_provider_and_key(self):
        sql = _merge_sql(ROOT, AGENTS_SCHEMA, 2)

        self.assertIn("MERGE INTO AGENTS.ROOT AS target", sql)
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

    def test_clickhouse_credentials_apply_defaults(self):
        kwargs = _clickhouse_connect_kwargs_from_secret(
            {"type": "clickhouse", "host": "abc.clickhouse.cloud"}
        )

        self.assertEqual(
            kwargs,
            {
                "host": "abc.clickhouse.cloud",
                "username": "default",
                "password": "",
                "secure": True,
            },
        )

    def test_clickhouse_credentials_accept_user_alias_port_and_plain_http(self):
        kwargs = _clickhouse_connect_kwargs_from_secret(
            {
                "type": "clickhouse",
                "host": "localhost",
                "username": "bot",
                "password": "pw",
                "port": "8123",
                "secure": False,
            }
        )

        self.assertEqual(kwargs["username"], "bot")
        self.assertEqual(kwargs["port"], 8123)
        self.assertFalse(kwargs["secure"])

    def test_clickhouse_credentials_parse_string_booleans_strictly(self):
        kwargs = _clickhouse_connect_kwargs_from_secret(
            {"type": "clickhouse", "host": "localhost", "password": "pw", "secure": "false"}
        )
        self.assertFalse(kwargs["secure"])

        with self.assertRaises(ConfigError):
            _clickhouse_connect_kwargs_from_secret(
                {"type": "clickhouse", "host": "localhost", "password": "pw", "secure": "maybe"}
            )

        with self.assertRaises(ConfigError):
            _clickhouse_connect_kwargs_from_secret(
                {"type": "clickhouse", "host": "localhost", "password": "pw", "secure": 1}
            )

    def test_clickhouse_credentials_validate_port(self):
        for port in (0, 65536, "not-a-port", 8123.5, True):
            with self.subTest(port=port), self.assertRaises(ConfigError):
                _clickhouse_connect_kwargs_from_secret(
                    {"type": "clickhouse", "host": "localhost", "port": port}
                )

    def test_clickhouse_credentials_require_host(self):
        with self.assertRaises(ConfigError):
            _clickhouse_connect_kwargs_from_secret({"type": "clickhouse", "password": "pw"})

    def test_clickhouse_destination_accepts_explicit_client(self):
        client = object()

        dest = ClickHouseDestination(client=client)

        self.assertIs(dest._client, client)

    def test_open_destination_supports_clickhouse(self):
        with patch("agents_schema.destinations.ClickHouseDestination") as destination:
            result = open_destination({"warehouse": {"type": "clickhouse"}})

        self.assertIs(result, destination.return_value)

    def test_bigquery_credentials_accept_object_shape(self):
        credentials, project_id, location = _bigquery_credentials_from_secret(
            {
                "type": "bigquery",
                "project_id": "analytics-project",
                "location": "US",
                "credentials_json": {
                    "type": "service_account",
                    "private_key": "key",
                    "client_email": "bot@example.com",
                },
            }
        )

        self.assertEqual(project_id, "analytics-project")
        self.assertEqual(location, "US")
        self.assertEqual(credentials["type"], "service_account")
        self.assertEqual(credentials["private_key"], "key")

    def test_bigquery_credentials_accept_json_string(self):
        credentials, project_id, _ = _bigquery_credentials_from_secret(
            {
                "type": "bigquery",
                "project_id": "analytics-project",
                "credentials_json": '{"private_key": "key", "client_email": "bot@example.com"}',
            }
        )

        self.assertEqual(project_id, "analytics-project")
        self.assertEqual(credentials["client_email"], "bot@example.com")

    def test_bigquery_credentials_accept_flattened_service_account_fields(self):
        credentials, project_id, _ = _bigquery_credentials_from_secret(
            {
                "type": "big_query",
                "project_id": "analytics-project",
                "private_key": "key",
                "client_email": "bot@example.com",
            }
        )

        self.assertEqual(project_id, "analytics-project")
        self.assertEqual(credentials["project_id"], "analytics-project")
        self.assertEqual(credentials["private_key"], "key")

    def test_bigquery_credentials_adc_short_circuits_service_account_lookup(self):
        credentials, project_id, location = _bigquery_credentials_from_secret(
            {
                "type": "bigquery",
                "project_id": "analytics-project",
                "auth_method": "adc",
            }
        )

        self.assertIsNone(credentials)
        self.assertEqual(project_id, "analytics-project")
        self.assertIsNone(location)

    def test_bigquery_credentials_adc_rejects_unknown_auth_method(self):
        with self.assertRaises(ConfigError):
            _bigquery_credentials_from_secret(
                {
                    "type": "bigquery",
                    "project_id": "analytics-project",
                    "auth_method": "oops",
                }
            )

    def test_bigquery_credentials_adc_rejects_leftover_service_account_fields(self):
        with self.assertRaises(ConfigError):
            _bigquery_credentials_from_secret(
                {
                    "type": "bigquery",
                    "project_id": "analytics-project",
                    "auth_method": "adc",
                    "credentials_json": {
                        "private_key": "key",
                        "client_email": "bot@example.com",
                    },
                }
            )

    def test_bigquery_destination_uses_adc_when_credentials_are_none(self):
        fake_credentials = object()
        with (
            patch(
                "agents_schema.destinations._bigquery_credentials",
                return_value=(None, "analytics-project", "US"),
            ),
            patch(
                "google.auth.default",
                return_value=(fake_credentials, "analytics-project"),
            ) as auth_default,
            patch("google.cloud.bigquery.Client") as client_cls,
        ):
            BigQueryDestination(config={"type": "bigquery"})

        auth_default.assert_called_once()
        client_cls.assert_called_once_with(credentials=fake_credentials, project="analytics-project")

    def test_bigquery_destination_accepts_explicit_client(self):
        client = object()

        dest = BigQueryDestination(client=client, project_id="analytics-project")

        self.assertIs(dest._client, client)
        self.assertEqual(dest._project_id, "analytics-project")

    def test_open_destination_supports_bigquery(self):
        with patch("agents_schema.destinations.BigQueryDestination") as destination:
            result = open_destination({"warehouse": {"type": "bigquery"}})

        self.assertIs(result, destination.return_value)

    def test_open_destination_supports_big_query_alias(self):
        with patch("agents_schema.destinations.BigQueryDestination") as destination:
            result = open_destination({"warehouse": {"type": "big_query"}})

        self.assertIs(result, destination.return_value)


if __name__ == "__main__":
    unittest.main()


class SnowflakeWorkloadIdentityTests(unittest.TestCase):
    BASE = {
        "type": "snowflake",
        "account": "acct",
        "user": "BOT",
        "warehouse": "WH",
        "database": "DB",
        "auth_method": "workload_identity",
    }

    def test_workload_identity_builds_oidc_connect_kwargs_without_static_credentials(self):
        with patch("agents_schema.destinations._github_oidc_token", return_value="jwt") as fetch:
            kwargs = _snowflake_connect_kwargs_from_secret({**self.BASE, "oidc_audience": "aud"})

        fetch.assert_called_once_with("aud")
        self.assertEqual(kwargs["authenticator"], "WORKLOAD_IDENTITY")
        self.assertEqual(kwargs["workload_identity_provider"], "OIDC")
        self.assertEqual(kwargs["token"], "jwt")
        self.assertNotIn("password", kwargs)
        self.assertNotIn("private_key", kwargs)

    def test_workload_identity_rejects_static_credentials(self):
        with self.assertRaisesRegex(ConfigError, "remove password"):
            _snowflake_connect_kwargs_from_secret({**self.BASE, "password": "pw"})

    def test_unknown_auth_method_is_rejected(self):
        with self.assertRaisesRegex(ConfigError, "auth_method must be .workload_identity."):
            _snowflake_connect_kwargs_from_secret({**self.BASE, "auth_method": "magic"})

    def test_github_oidc_token_requires_actions_environment(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ConfigError, "id-token: write"):
                _github_oidc_token(None)

    def test_password_auth_is_unchanged(self):
        kwargs = _snowflake_connect_kwargs_from_secret(
            {k: v for k, v in self.BASE.items() if k != "auth_method"} | {"password": "pw"}
        )
        self.assertEqual(kwargs["password"], "pw")
        self.assertNotIn("authenticator", kwargs)

    def _fetch_token(self, urlopen_result=None, side_effect=None, audience=None):
        env = {
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://actions.example/token?api-version=2",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "req",
        }
        with patch.dict("os.environ", env, clear=True), patch("time.sleep"), patch(
            "urllib.request.urlopen", return_value=urlopen_result, side_effect=side_effect
        ) as urlopen:
            return _github_oidc_token(audience), urlopen

    def test_github_oidc_token_requests_audience(self):
        token, urlopen = self._fetch_token(
            io.BytesIO(b'{"value": "jwt"}'), audience="https://acct.snowflakecomputing.com"
        )

        self.assertEqual(token, "jwt")
        request = urlopen.call_args.args[0]
        self.assertIn("audience=https%3A%2F%2Facct.snowflakecomputing.com", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "Bearer req")

    def test_github_oidc_token_defaults_to_snowflake_audience(self):
        token, urlopen = self._fetch_token(io.BytesIO(b'{"value": "jwt"}'))

        self.assertEqual(token, "jwt")
        self.assertIn("audience=snowflakecomputing.com", urlopen.call_args.args[0].full_url)

    def test_github_oidc_token_request_failure_is_a_config_error(self):
        with self.assertRaisesRegex(ConfigError, "Failed to fetch GitHub Actions OIDC token"):
            self._fetch_token(side_effect=OSError("boom"))

    def test_github_oidc_token_response_without_value_is_a_config_error(self):
        with self.assertRaisesRegex(ConfigError, "did not include a token"):
            self._fetch_token(io.BytesIO(b"{}"))

    @staticmethod
    def _http_error(code):
        return urllib.error.HTTPError("https://actions.example/token", code, "err", {}, None)

    def test_github_oidc_token_http_client_error_is_not_retried(self):
        calls = []

        def forbidden(*args, **kwargs):
            calls.append(1)
            raise self._http_error(403)

        with self.assertRaisesRegex(ConfigError, "HTTP 403"):
            self._fetch_token(side_effect=forbidden)
        self.assertEqual(len(calls), 1)

    def test_github_oidc_token_server_error_is_retried_then_fails(self):
        urlopen_calls = []

        def fail(*args, **kwargs):
            urlopen_calls.append(1)
            raise self._http_error(503)

        with self.assertRaisesRegex(ConfigError, "HTTP 503"):
            self._fetch_token(side_effect=fail)
        self.assertEqual(len(urlopen_calls), 3)

    def test_github_oidc_token_recovers_from_a_transient_failure(self):
        responses = [self._http_error(502), io.BytesIO(b'{"value": "jwt"}')]

        def respond(*args, **kwargs):
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        token, _ = self._fetch_token(side_effect=respond)
        self.assertEqual(token, "jwt")

    def test_github_oidc_token_rejects_non_https_request_url(self):
        env = {
            "ACTIONS_ID_TOKEN_REQUEST_URL": "http://actions.example/token",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "req",
        }
        with patch.dict("os.environ", env, clear=True), self.assertRaisesRegex(ConfigError, "https"):
            _github_oidc_token(None)

    def test_github_oidc_token_response_that_is_not_an_object_is_rejected(self):
        with self.assertRaisesRegex(ConfigError, "did not include a token"):
            self._fetch_token(io.BytesIO(b'["jwt"]'))

    def test_workload_identity_rejects_blank_audience(self):
        with self.assertRaisesRegex(ConfigError, "oidc_audience"):
            _snowflake_connect_kwargs_from_secret({**self.BASE, "oidc_audience": "  "})

    def test_destination_explains_unrecognized_oidc_token_and_masks_it(self):
        import snowflake.connector.errors as sf_errors

        error = sf_errors.DatabaseError(msg="subject 'sub-x' not recognized token=SECRET.JWT", errno=394729)
        kwargs = {"authenticator": "WORKLOAD_IDENTITY", "token": "SECRET.JWT"}
        with patch("snowflake.connector.connect", side_effect=error):
            with self.assertRaises(ConfigError) as ctx:
                SnowflakeDestination(connect_kwargs=kwargs)

        message = str(ctx.exception)
        self.assertIn("sub-x", message)
        self.assertIn("OIDC_AUDIENCE_LIST", message)
        self.assertNotIn("SECRET.JWT", message)
        self.assertIs(ctx.exception.__cause__, error)

    def test_destination_leaves_other_snowflake_errors_untouched(self):
        import snowflake.connector.errors as sf_errors

        error = sf_errors.DatabaseError(msg="bad password", errno=390100)
        with patch("snowflake.connector.connect", side_effect=error):
            with self.assertRaises(sf_errors.DatabaseError):
                SnowflakeDestination(connect_kwargs={"account": "a", "password": "p"})

    def test_destination_explains_disallowed_audience(self):
        import snowflake.connector.errors as sf_errors

        error = sf_errors.DatabaseError(msg="JWT contains an invalid audience ('aud') claim", errno=394728)
        with patch("snowflake.connector.connect", side_effect=error):
            with self.assertRaises(ConfigError) as ctx:
                SnowflakeDestination(connect_kwargs={"authenticator": "WORKLOAD_IDENTITY", "token": "t"})

        self.assertIn("invalid audience", str(ctx.exception))
        self.assertIn("oidc_audience", str(ctx.exception))
