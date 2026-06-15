from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable

from .schema import TableSchema


class AgentsSchemaWriter(ABC):
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

    def __enter__(self) -> "AgentsSchemaWriter":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()
