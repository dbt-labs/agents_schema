"""Registry for metadata export connector modules."""
from __future__ import annotations

from typing import Any, Callable

from . import (
    alation,
    atlan,
    collibra,
    cube,
    datahub,
    dbt_semantic,
    metabase,
    openmetadata,
    powerbi,
    tableau,
)

__all__ = ["SUPPORTED_PROVIDERS", "run"]

SUPPORTED_PROVIDERS: dict[str, Callable[[dict[str, Any]], None]] = {
    "powerbi": powerbi.run,
    "tableau": tableau.run,
    "dbt_semantic": dbt_semantic.run,
    "datahub": datahub.run,
    "openmetadata": openmetadata.run,
    "atlan": atlan.run,
    "alation": alation.run,
    "collibra": collibra.run,
    "metabase": metabase.run,
    "cube": cube.run,
}


def run(provider_name: str, cfg: dict[str, Any]) -> None:
    SUPPORTED_PROVIDERS[provider_name](cfg)
