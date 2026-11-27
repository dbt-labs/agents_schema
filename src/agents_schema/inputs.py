"""Helpers shared by the source connectors."""
from __future__ import annotations

from typing import Any, Callable

__all__ = ["parse_input"]


def parse_input(source: str, collect: Callable[..., Any], *args: Any) -> Any:
    """Run a connector's pure parse step on its input.

    A file that is valid YAML or JSON but not shaped as the connector expects (for example `pages: null`
    or a list where a mapping belongs) would otherwise escape as a raw AttributeError or TypeError
    traceback. It becomes a ValueError, which the CLI reports as `agents-schema: error: ...`. The original
    exception stays chained for debugging.
    """
    try:
        return collect(*args)
    except (AttributeError, TypeError, KeyError, IndexError) as e:
        raise ValueError(f"{source}: input is not in the expected shape ({type(e).__name__}: {e})") from e
