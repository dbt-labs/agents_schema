"""Warehouse destinations for agents-schema writes."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from .agents_schema_writer import (
    AgentsSchemaWriter,
    Column,
    DatabricksAgentsSchemaWriter,
    SnowflakeAgentsSchemaWriter,
    TableSchema,
)
from .agents_schema_writer.snowflake import (
    _create_table_if_not_exists_sql,
    _create_table_sql,
    _delete_sql,
    _insert_sql,
    _merge_sql,
    load_private_key,
)
from .config import ConfigError, SUPPORTED_WAREHOUSE_TYPES, warehouse_type

Destination = AgentsSchemaWriter


class SnowflakeDestination(SnowflakeAgentsSchemaWriter):
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        connect_kwargs: dict[str, Any] | None = None,
    ) -> None:
        import snowflake.connector

        if connect_kwargs is None:
            if config is None:
                raise ConfigError("SnowflakeDestination requires config or connect_kwargs")
            connect_kwargs = _snowflake_connect_kwargs(config)
        super().__init__(snowflake.connector.connect(**connect_kwargs))


class DatabricksDestination(DatabricksAgentsSchemaWriter):
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        connect_kwargs: dict[str, Any] | None = None,
    ) -> None:
        import databricks.sql

        if connect_kwargs is None:
            if config is None:
                raise ConfigError("DatabricksDestination requires config or connect_kwargs")
            connect_kwargs = _databricks_connect_kwargs(config)
        super().__init__(databricks.sql.connect(**connect_kwargs))


def open_destination(cfg: dict[str, Any]) -> Destination:
    dest_type = warehouse_type(cfg)
    if dest_type == "snowflake":
        return SnowflakeDestination(cfg)
    if dest_type == "databricks":
        return DatabricksDestination(cfg)
    raise ConfigError(f"unsupported destination type: {dest_type}")


def warehouse_credentials_from_env() -> dict[str, Any]:
    raw = os.environ.get("WAREHOUSE_CREDENTIALS")
    if not raw:
        raise ConfigError("missing required WAREHOUSE_CREDENTIALS secret")
    destination = _parse_warehouse_credentials(raw)
    destination_type = destination.get("type")
    if not isinstance(destination_type, str) or not destination_type:
        raise ConfigError("WAREHOUSE_CREDENTIALS.type is required")
    if destination_type not in SUPPORTED_WAREHOUSE_TYPES:
        supported = ", ".join(sorted(SUPPORTED_WAREHOUSE_TYPES))
        raise ConfigError(
            f"unsupported WAREHOUSE_CREDENTIALS.type {destination_type!r}; supported types: {supported}"
        )
    return destination


def warehouse_type_from_env() -> str:
    return str(warehouse_credentials_from_env()["type"])


def _parse_warehouse_credentials(raw: str) -> dict[str, Any]:
    try:
        destination = json.loads(raw)
    except json.JSONDecodeError:
        try:
            destination = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            raise ConfigError(f"WAREHOUSE_CREDENTIALS is not valid JSON or YAML: {e}") from e
    if not isinstance(destination, dict):
        raise ConfigError("WAREHOUSE_CREDENTIALS must be a JSON or YAML object")
    return destination


def _snowflake_connect_kwargs(cfg: dict[str, Any]) -> dict[str, Any]:
    destination = warehouse_credentials_from_env()
    if destination.get("type") != "snowflake":
        raise ConfigError("WAREHOUSE_CREDENTIALS.type must be snowflake")
    return _snowflake_connect_kwargs_from_secret(destination)


def _snowflake_connect_kwargs_from_secret(destination: dict[str, Any]) -> dict[str, Any]:
    required = ["account", "user", "warehouse", "database"]
    missing = [name for name in required if not destination.get(name)]
    has_password = bool(destination.get("password"))
    has_private_key_pem = bool(destination.get("private_key_pem"))
    has_private_key_path = bool(destination.get("private_key_path"))
    if not has_password and not has_private_key_pem and not has_private_key_path:
        missing.append("password, private_key_pem, or private_key_path")
    if missing:
        raise ConfigError("WAREHOUSE_CREDENTIALS missing keys: " + ", ".join(missing))

    kwargs: dict[str, Any] = {
        "account": destination["account"],
        "user": destination["user"],
        "warehouse": destination["warehouse"],
        "database": destination["database"],
    }
    if role := destination.get("role"):
        kwargs["role"] = role
    passphrase = destination.get("private_key_passphrase")
    if has_private_key_pem:
        kwargs["private_key"] = load_private_key(
            destination["private_key_pem"].encode(),
            passphrase,
        )
    elif has_private_key_path:
        kwargs["private_key"] = load_private_key(
            Path(destination["private_key_path"]).read_bytes(),
            passphrase,
        )
    else:
        kwargs["password"] = destination["password"]
    return kwargs


def _databricks_connect_kwargs(cfg: dict[str, Any]) -> dict[str, Any]:
    destination = warehouse_credentials_from_env()
    if destination.get("type") != "databricks":
        raise ConfigError("WAREHOUSE_CREDENTIALS.type must be databricks")
    return _databricks_connect_kwargs_from_secret(destination)


def _databricks_connect_kwargs_from_secret(destination: dict[str, Any]) -> dict[str, Any]:
    host = (
        destination.get("host")
        or destination.get("server_host_name")
        or destination.get("serverHostName")
    )
    token = (
        destination.get("token")
        or destination.get("access_token")
        or destination.get("personal_access_token")
        or destination.get("personalAccessToken")
    )
    required = {
        "host": host,
        "http_path": destination.get("http_path") or destination.get("httpPath"),
        "catalog": destination.get("catalog"),
        "token": token,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ConfigError("WAREHOUSE_CREDENTIALS missing keys: " + ", ".join(missing))

    return {
        "server_hostname": required["host"],
        "http_path": required["http_path"],
        "catalog": required["catalog"],
        "access_token": required["token"],
    }


__all__ = [
    "Column",
    "DatabricksDestination",
    "Destination",
    "SnowflakeDestination",
    "TableSchema",
    "_create_table_if_not_exists_sql",
    "_create_table_sql",
    "_databricks_connect_kwargs_from_secret",
    "_delete_sql",
    "_insert_sql",
    "_merge_sql",
    "_snowflake_connect_kwargs_from_secret",
    "open_destination",
    "warehouse_credentials_from_env",
    "warehouse_type_from_env",
]
