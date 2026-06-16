from __future__ import annotations

from typing import Any, Iterable
from uuid import uuid4

from agents_schema.config import ConfigError

from .base import AgentsSchemaWriter
from .schema import AGENTS_SCHEMA, Column, TableSchema
from .utils import rows_json_for_table


class BigQueryAgentsSchemaWriter(AgentsSchemaWriter):
    def __init__(self, client: Any, project_id: str, location: str | None = None) -> None:
        from google.cloud import bigquery

        self._client = client
        self._project_id = project_id
        self._location = location
        self._bigquery = bigquery

    def ensure_table(self, table: TableSchema) -> None:
        self._ensure_dataset()
        schema = [_bigquery_schema_field(self._bigquery, column) for column in table.columns]
        self._client.create_table(self._bigquery.Table(self._table_ref(table), schema=schema), exists_ok=True)

    def replace_table(self, table: TableSchema) -> None:
        self._ensure_dataset()
        schema = [_bigquery_schema_field(self._bigquery, column) for column in table.columns]
        self._client.delete_table(self._table_ref(table), not_found_ok=True)
        self._client.create_table(self._bigquery.Table(self._table_ref(table), schema=schema))

    def delete_rows(
        self,
        table: TableSchema,
        key_columns: tuple[str, ...],
        rows: Iterable[tuple[Any, ...]],
    ) -> None:
        if not key_columns:
            raise ConfigError("delete requires at least one key column")
        self.ensure_table(table)
        for row in rows:
            where_sql = " AND ".join(f"`{column}` = @p{index}" for index, column in enumerate(key_columns))
            job_config = self._bigquery.QueryJobConfig(
                query_parameters=[
                    self._bigquery.ScalarQueryParameter(f"p{index}", "STRING", value)
                    for index, value in enumerate(row)
                ]
            )
            self._client.query(f"DELETE FROM `{self._table_ref(table)}` WHERE {where_sql}", job_config=job_config).result()

    def insert_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None:
        rows_json = rows_json_for_table(table, rows)
        if not rows_json:
            return
        job_config = self._bigquery.LoadJobConfig(
            schema=[_bigquery_schema_field(self._bigquery, column) for column in table.columns],
            write_disposition=self._bigquery.WriteDisposition.WRITE_APPEND,
        )
        self._client.load_table_from_json(rows_json, self._table_ref(table), job_config=job_config).result()

    def upsert_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None:
        self.ensure_table(table)
        rows_json = rows_json_for_table(table, rows)
        if not rows_json:
            return
        staging_ref = self._staging_ref(table)
        job_config = self._bigquery.LoadJobConfig(
            schema=[_bigquery_schema_field(self._bigquery, column) for column in table.columns],
            write_disposition=self._bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        try:
            self._client.load_table_from_json(rows_json, staging_ref, job_config=job_config).result()
            self._client.query(self._merge_sql(table, staging_ref)).result()
        finally:
            self._client.delete_table(staging_ref, not_found_ok=True)

    def reconcile_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None:
        self.ensure_table(table)
        rows_json = rows_json_for_table(table, rows)
        if not rows_json:
            self._client.query(f"DELETE FROM `{self._table_ref(table)}` WHERE TRUE").result()
            return
        staging_ref = self._staging_ref(table)
        job_config = self._bigquery.LoadJobConfig(
            schema=[_bigquery_schema_field(self._bigquery, column) for column in table.columns],
            write_disposition=self._bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        try:
            self._client.load_table_from_json(rows_json, staging_ref, job_config=job_config).result()
            self._client.query(self._merge_sql(table, staging_ref, delete_absent=True)).result()
        finally:
            self._client.delete_table(staging_ref, not_found_ok=True)

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if close is not None:
            close()

    def _ensure_dataset(self) -> None:
        dataset = self._bigquery.Dataset(f"{self._project_id}.{AGENTS_SCHEMA}")
        if self._location:
            dataset.location = self._location
        self._client.create_dataset(dataset, exists_ok=True)

    def _table_ref(self, table: TableSchema) -> str:
        return f"{self._project_id}.{AGENTS_SCHEMA}.{table.base_name}"

    def _staging_ref(self, table: TableSchema) -> str:
        return f"{self._project_id}.{AGENTS_SCHEMA}._staging_{table.base_name}_{uuid4().hex}"

    def _merge_sql(self, table: TableSchema, staging_ref: str, delete_absent: bool = False) -> str:
        if not table.primary_key:
            raise ConfigError("upsert requires a table primary key")
        columns = [column.name for column in table.columns]
        non_key_columns = [column for column in columns if column not in table.primary_key]
        on_sql = " AND ".join(f"target.`{column}` = source.`{column}`" for column in table.primary_key)
        update_sql = ", ".join(f"`{column}` = source.`{column}`" for column in non_key_columns)
        insert_columns = ", ".join(f"`{column}`" for column in columns)
        insert_values = ", ".join(f"source.`{column}`" for column in columns)
        matched_sql = f"WHEN MATCHED THEN UPDATE SET {update_sql}\n" if update_sql else ""
        delete_sql = "\nWHEN NOT MATCHED BY SOURCE THEN DELETE" if delete_absent else ""
        return f"""MERGE `{self._table_ref(table)}` AS target
USING `{staging_ref}` AS source
ON {on_sql}
{matched_sql}WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values})
{delete_sql}
"""


def _bigquery_schema_field(bigquery: Any, column: Column) -> Any:
    if column.kind == "array":
        return bigquery.SchemaField(column.name, "STRING", mode="REPEATED")
    mode = "NULLABLE" if column.nullable else "REQUIRED"
    return bigquery.SchemaField(column.name, _bigquery_type(column), mode=mode)


def _bigquery_type(column: Column) -> str:
    if column.kind == "boolean":
        return "BOOL"
    if column.kind in {"text", "varchar"}:
        return "STRING"
    raise ValueError(f"unsupported column kind: {column.kind}")
