from __future__ import annotations

from dataclasses import dataclass

AGENTS_SCHEMA = "agents"


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
        return {index for index, column in enumerate(self.columns) if column.kind == "array"}

    @property
    def base_name(self) -> str:
        return self.name.split(".")[-1]
