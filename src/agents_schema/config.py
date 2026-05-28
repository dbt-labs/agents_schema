"""Shared configuration validation for agents-schema."""
from __future__ import annotations

from typing import Any


class ConfigError(Exception):
    """Raised when CLI arguments or environment settings are invalid."""


def warehouse_type(cfg: dict[str, Any]) -> str:
    warehouse = cfg.get("warehouse")
    if warehouse is None:
        return "snowflake"
    if not isinstance(warehouse, dict):
        raise ConfigError("warehouse must be a mapping when provided")
    wh_type = warehouse.get("type", "snowflake")
    if wh_type != "snowflake":
        raise ConfigError("warehouse.type must be snowflake")
    return wh_type
