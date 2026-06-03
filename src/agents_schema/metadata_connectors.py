"""Registry for metadata export connector modules."""
from __future__ import annotations

from typing import Any, Callable

from . import powerbi

__all__ = ["SUPPORTED_PROVIDERS", "run"]

SUPPORTED_PROVIDERS: dict[str, Callable[[dict[str, Any]], None]] = {
    "powerbi": powerbi.run,
}


def run(provider_name: str, cfg: dict[str, Any]) -> None:
    SUPPORTED_PROVIDERS[provider_name](cfg)
