from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any, Self

from .schema import TableSchema


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
    def reconcile_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    def __enter__(self) -> Self:
        self.prepare()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()
