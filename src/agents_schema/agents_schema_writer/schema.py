from __future__ import annotations

from dataclasses import dataclass

AGENTS_SCHEMA = "AGENTS"


@dataclass(frozen=True)
class Column:
    name: str
    kind: str
    nullable: bool = True


@dataclass(frozen=True)
class RowScope:
    """The slice of a shared table that one caller owns, such as one provider's skill rows in AGENTS.ROOT.

    A row is in scope when every `equals` column has exactly that value and every `starts_with`
    column starts with that prefix.
    """

    equals: tuple[tuple[str, str], ...] = ()
    starts_with: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        # An empty scope would mean "the whole table" (or, with an empty prefix, every row of a provider),
        # and the delete-absent step would remove everything the caller did not just write.
        if not self.equals and not self.starts_with:
            raise ValueError("RowScope needs at least one term; an empty scope would match the whole table")
        for column, prefix in self.starts_with:
            if not prefix:
                raise ValueError(f"RowScope prefix for {column!r} must not be empty")


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
