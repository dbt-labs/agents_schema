"""Helpers for reading source metadata export files."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .config import ConfigError

SUPPORTED_METADATA_SUFFIXES = {".json", ".yaml", ".yml"}


def load_metadata_documents(path: Path) -> list[Any]:
    """Load one metadata export file, or every supported file below a directory."""
    if path.is_file():
        return [_load_metadata_file(path)]
    if not path.exists():
        raise FileNotFoundError(f"metadata path not found: {path}")
    if not path.is_dir():
        raise ConfigError(f"metadata path must be a file or directory: {path}")

    files = sorted(p for p in path.rglob("*") if p.suffix.lower() in SUPPORTED_METADATA_SUFFIXES)
    if not files:
        suffixes = ", ".join(sorted(SUPPORTED_METADATA_SUFFIXES))
        raise FileNotFoundError(f"no metadata export files ({suffixes}) found in {path}")
    return [_load_metadata_file(file_path) for file_path in files]


def _load_metadata_file(path: Path) -> Any:
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError as e:
            raise ConfigError(f"{path} is not valid JSON: {e}") from e
    if suffix in {".yaml", ".yml"}:
        try:
            return yaml.safe_load(path.read_text())
        except yaml.YAMLError as e:
            raise ConfigError(f"{path} is not valid YAML: {e}") from e
    raise ConfigError(f"unsupported metadata file type for {path}")
