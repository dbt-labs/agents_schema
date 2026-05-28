"""agents-schema: populate the agents.* warehouse schema for AI consumption."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("agents-schema")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
