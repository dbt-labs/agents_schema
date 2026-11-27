from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from contextlib import suppress
from typing import Any, Self

from .schema import RowScope, TableSchema


class AgentsSchemaWriter(ABC):
    def prepare(self) -> None:
        """Run idempotent destination-specific setup before the first write."""

    @abstractmethod
    def ensure_table(self, table: TableSchema) -> None: ...

    @abstractmethod
    def replace_table(self, table: TableSchema) -> None: ...

    @abstractmethod
    def upsert_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None: ...

    @abstractmethod
    def insert_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None: ...

    @abstractmethod
    def delete_rows(
        self,
        table: TableSchema,
        key_columns: tuple[str, ...],
        rows: Iterable[tuple[Any, ...]],
    ) -> None: ...

    @abstractmethod
    def reconcile_rows(
        self,
        table: TableSchema,
        rows: Iterable[tuple[Any, ...]],
        scope: RowScope | None = None,
    ) -> None:
        """Upsert `rows`, then delete rows that are absent from them.

        Without `scope` the whole table is reconciled, so use that only on a table one caller
        owns. With `scope`, only rows inside the scope are candidates for deletion, so a caller
        can keep its own slice of a shared table (one provider's skills in AGENTS.ROOT) in sync
        without touching anyone else's rows. Every row passed in must be inside the scope.
        """

    @abstractmethod
    def close(self) -> None: ...

    def __enter__(self) -> Self:
        try:
            self.prepare()
        except BaseException:
            with suppress(Exception):
                self.close()
            raise
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()
