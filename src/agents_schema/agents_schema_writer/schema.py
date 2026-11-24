from __future__ import annotations

from dataclasses import dataclass

AGENTS_SCHEMA = "AGENTS"


@dataclass(frozen=True)
class Column:
    name: str
    kind: str
    nullable: bool = True


@dataclass(frozen=True)
class TableSchema:
    name: str
    columns: tuple[Column, ...]
    primary_key: tuple[str, ...] = ()

    @property
    def array_indexes(self) -> set[int]:
        # "variant" holds arbitrary JSON (a string, object, or array). Destinations without a
        # better native type handle it exactly like "array", so both share this code path.
        return {index for index, column in enumerate(self.columns) if column.kind in {"array", "variant"}}

    @property
    def json_indexes(self) -> set[int]:
        return {index for index, column in enumerate(self.columns) if column.kind == "json"}

    @property
    def base_name(self) -> str:
        return self.name.split(".")[-1]
