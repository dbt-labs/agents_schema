from __future__ import annotations

import warnings
from collections.abc import Iterable
from copy import deepcopy
from typing import Any
from uuid import uuid4

from google.api_core.exceptions import Conflict, Forbidden, NotFound

from agents_schema.config import ConfigError

from .base import AgentsSchemaWriter
from .schema import AGENTS_SCHEMA, Column, TableSchema
from .utils import rows_json_for_table

LEGACY_AGENTS_SCHEMA = "agents"
_COPYABLE_TABLE_TYPES = {"TABLE"}
_MIGRATED_DATASET_PROPERTIES = (
    "access_entries",
    "access_policy_version",
    "default_encryption_configuration",
    "default_partition_expiration_ms",
    "default_rounding_mode",
    "default_table_expiration_ms",
    "description",
    "friendly_name",
    "labels",
    "max_time_travel_hours",
    "resource_tags",
    "storage_billing_model",
)


class BigQueryAgentsSchemaWriter(AgentsSchemaWriter):
    def __init__(self, client: Any, project_id: str, location: str | None = None) -> None:
        from google.cloud import bigquery

        self._client = client
        self._project_id = project_id
        self._location = location
        self._bigquery = bigquery
        self._prepared = False

    def prepare(self) -> None:
        """Create AGENTS and non-destructively copy missing legacy tables."""
        if self._prepared:
            return

        legacy_ref = f"{self._project_id}.{LEGACY_AGENTS_SCHEMA}"
        target_ref = f"{self._project_id}.{AGENTS_SCHEMA}"
        legacy = self._get_dataset_or_none(legacy_ref)
        target = self._get_dataset_or_none(target_ref)

        if legacy is not None and self._location:
            self._require_same_location(self._location, legacy.location, legacy_ref, target_ref)

        if target is None:
            dataset = self._bigquery.Dataset(target_ref)
            dataset.location = legacy.location if legacy is not None else self._location
            if legacy is not None:
                self._copy_dataset_properties(legacy, dataset)
            target = self._client.create_dataset(dataset, exists_ok=True) or dataset

        if legacy is not None and not self._same_dataset(legacy, target):
            self._require_same_location(legacy.location, target.location, legacy_ref, target_ref)
            self._copy_missing_legacy_tables(legacy_ref, target_ref, target.location)
            self._warn_for_unsupported_resources(legacy_ref)

        self._prepared = True

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
        self.prepare()
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
        self.prepare()

    def _get_dataset_or_none(self, dataset_ref: str) -> Any | None:
        try:
            return self._client.get_dataset(dataset_ref)
        except NotFound:
            return None

    def _same_dataset(self, left: Any, right: Any) -> bool:
        return (
            getattr(left, "project", self._project_id) == getattr(right, "project", self._project_id)
            and getattr(left, "dataset_id", None) == getattr(right, "dataset_id", None)
        )

    def _require_same_location(
        self,
        source_location: str | None,
        target_location: str | None,
        source_ref: str,
        target_ref: str,
    ) -> None:
        if source_location and target_location and source_location.casefold() != target_location.casefold():
            raise ConfigError(
                f"cannot migrate BigQuery dataset {source_ref} in {source_location} "
                f"to {target_ref} in {target_location}"
            )

    def _copy_dataset_properties(self, source: Any, target: Any) -> None:
        for property_name in _MIGRATED_DATASET_PROPERTIES:
            if hasattr(source, property_name) and hasattr(target, property_name):
                value = getattr(source, property_name)
                if value is None or (isinstance(value, str) and value.endswith("_UNSPECIFIED")):
                    continue
                setattr(target, property_name, deepcopy(value))

    def _copy_missing_legacy_tables(
        self,
        legacy_ref: str,
        target_ref: str,
        location: str | None,
    ) -> None:
        legacy_tables = sorted(self._client.list_tables(legacy_ref), key=lambda table: table.table_id)
        target_table_ids = {table.table_id for table in self._client.list_tables(target_ref)}
        canonical_sources: dict[str, str] = {}
        copied = 0

        for table in legacy_tables:
            source_table_id = table.table_id
            if source_table_id.casefold().startswith("_staging_"):
                continue

            target_table_id = source_table_id.upper()
            previous_source = canonical_sources.setdefault(target_table_id, source_table_id)
            if previous_source != source_table_id:
                raise ConfigError(
                    "cannot migrate BigQuery tables with colliding canonical names: "
                    f"{legacy_ref}.{previous_source} and {legacy_ref}.{source_table_id}"
                )
            if target_table_id in target_table_ids:
                continue

            table_type = str(getattr(table, "table_type", "TABLE") or "TABLE").upper()
            if table_type not in _COPYABLE_TABLE_TYPES:
                warnings.warn(
                    f"BigQuery migration skipped unsupported {table_type} object "
                    f"{legacy_ref}.{source_table_id}; migrate it manually",
                    RuntimeWarning,
                    stacklevel=2,
                )
                continue

            source_table_ref = f"{legacy_ref}.{source_table_id}"
            target_table_ref = f"{target_ref}.{target_table_id}"
            job_config = self._bigquery.CopyJobConfig(
                write_disposition=self._bigquery.WriteDisposition.WRITE_EMPTY
            )
            try:
                self._client.copy_table(
                    source_table_ref,
                    target_table_ref,
                    job_config=job_config,
                    location=location,
                ).result()
            except Conflict:
                if not self._table_exists(target_table_ref):
                    raise
            else:
                copied += 1
            target_table_ids.add(target_table_id)

        if copied:
            print(
                f"  bigquery: migrated {copied} table(s) from "
                f"{LEGACY_AGENTS_SCHEMA} to {AGENTS_SCHEMA}"
            )

    def _warn_for_unsupported_resources(self, legacy_ref: str) -> None:
        self._warn_for_unsupported_collection(
            legacy_ref,
            object_type="ROUTINE",
            id_attribute="routine_id",
            list_method_name="list_routines",
        )
        self._warn_for_unsupported_collection(
            legacy_ref,
            object_type="MODEL",
            id_attribute="model_id",
            list_method_name="list_models",
        )

    def _warn_for_unsupported_collection(
        self,
        legacy_ref: str,
        *,
        object_type: str,
        id_attribute: str,
        list_method_name: str,
    ) -> None:
        list_method = getattr(self._client, list_method_name, None)
        if list_method is None:
            warnings.warn(
                f"BigQuery migration could not inventory legacy {object_type.lower()}s; "
                f"the installed client does not support {list_method_name}",
                RuntimeWarning,
                stacklevel=2,
            )
            return

        try:
            objects = list_method(legacy_ref)
            for item in objects:
                object_id = getattr(item, id_attribute)
                warnings.warn(
                    f"BigQuery migration skipped unsupported {object_type} object "
                    f"{legacy_ref}.{object_id}; migrate it manually",
                    RuntimeWarning,
                    stacklevel=2,
                )
        except Forbidden:
            warnings.warn(
                f"BigQuery migration could not inventory legacy {object_type.lower()}s in "
                f"{legacy_ref}; grant the corresponding list permission or inspect them manually",
                RuntimeWarning,
                stacklevel=2,
            )

    def _table_exists(self, table_ref: str) -> bool:
        try:
            self._client.get_table(table_ref)
        except NotFound:
            return False
        return True

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
    if column.kind == "json":
        return "JSON"
    if column.kind in {"text", "varchar"}:
        return "STRING"
    raise ValueError(f"unsupported column kind: {column.kind}")
