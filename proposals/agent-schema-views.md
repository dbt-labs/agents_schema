# Agents Schema Context Views Proposal

**Status:** Proposal
**Branch:** `agent_schema_views`

## Summary

Add information-schema-like views to Agents Schema so agents can query richer metadata through familiar object names:

```sql
AGENTS.TABLES
AGENTS.COLUMNS
AGENTS.RELATIONSHIPS
AGENTS.METRICS
AGENTS.ENTITIES
```

The goal is to make Agents Schema instantly swappable for common `INFORMATION_SCHEMA` exploration patterns while adding richer context. Anywhere an agent would normally ask `INFORMATION_SCHEMA.TABLES` or `INFORMATION_SCHEMA.COLUMNS`, it should be able to ask `AGENTS.TABLES` or `AGENTS.COLUMNS` instead and get the familiar shape plus dbt descriptions, LookML/OSI semantic metadata, source provider references, and eventually profiling or usage context.

## v1 Scope (Implemented)

The shipped v1 is deliberately narrower than the full proposal below, which is retained as the longer-term design sketch.

- **Only the surfaces `INFORMATION_SCHEMA` already has — `AGENTS.TABLES` and `AGENTS.COLUMNS`.** `RELATIONSHIPS`, `METRICS`, and `ENTITIES` are deferred. They are *new* object types that semantic providers like OSI already model in their own tables; adding generic versions now would make this a competing semantic model rather than an information-schema extension. The information-schema-faithful home for relationships is the `REFERENTIAL_CONSTRAINTS` / `KEY_COLUMN_USAGE` family, which is the intended future shape rather than a custom `AGENTS.RELATIONSHIPS` view.
- **Native spine via `SELECT t.*`.** `AGENTS.TABLES`/`COLUMNS` select `t.*` from `INFORMATION_SCHEMA.TABLES`/`COLUMNS` and inherit whatever native columns the account exposes. No native column list is hardcoded.
- **Generic identity merge.** Each provider's `*_TABLES`/`*_COLUMNS` view is left joined by object identity (catalog/schema/table, plus column for columns), with its enrichment columns appended under a `<provider>_` prefix. The set of providers is discovered, not hardcoded. Within a provider, rows are aggregated to one per identity to prevent fanout.
- **No hardcoded memory counts.** Memory participation is purely additive: when a memory provider later publishes its own `*_TABLES`/`*_COLUMNS` view exposing counts, those columns appear automatically. The core views contain no memory-specific logic.
- **Fail-soft.** View creation runs at the end of each provider ingestion but never fails the ingestion; a view error warns and is skipped.

## Motivation

Most SQL agents already know to inspect:

```sql
INFORMATION_SCHEMA.TABLES
INFORMATION_SCHEMA.COLUMNS
```

But native information schema is too thin for analytic work. It can tell an agent that a column exists, but not:

- which dbt model documented it
- whether it has LookML or OSI semantic context
- which metric uses it
- whether joining it causes fanout
- whether amounts need scaling
- whether a table is a semantic dataset, staging table, or source mirror

Agents Schema already has source-specific tables. Context views would provide a generic layer over them.

## Design Principles

- **Views, not new source of truth.** Source provider tables remain canonical.
- **Information-schema swappable.** Preserve familiar view names and core columns so agents can reuse existing `INFORMATION_SCHEMA` habits with a richer source.
- **Provider-owned normalization.** Providers publish their own `AGENTS.<PROVIDER>_TABLES`, `AGENTS.<PROVIDER>_COLUMNS`, and related normalized views when they want to participate in the generic layer.
- **Provider-aware.** Preserve `source_provider` and `source_object_id` so agents can drill down.
- **Composable with memory.** If the memory provider exists, views can expose memory/warning counts and optional compact memory text.
- **Sparse first.** Start with dbt/LookML/OSI fields already available today; add warehouse-native metadata later.

## Proposed Views

The first columns in each view should intentionally resemble the equivalent `INFORMATION_SCHEMA` view where one exists. Agents and existing metadata snippets should be able to select familiar columns first, then opt into the extended columns.

Core generic views should not directly know every source table. Instead, each provider maps its native metadata into provider-normalized views with the shared shape:

```text
AGENTS.DBT_TABLES
AGENTS.DBT_COLUMNS
AGENTS.DBT_RELATIONSHIPS
AGENTS.LOOKML_TABLES
AGENTS.LOOKML_COLUMNS
AGENTS.LOOKML_METRICS
AGENTS.OSI_TABLES
AGENTS.OSI_COLUMNS
AGENTS.OSI_RELATIONSHIPS
AGENTS.OSI_METRICS
```

Then `AGENTS.TABLES` is a merged information-schema view over every provider `*_TABLES` view:

```text
AGENTS.TABLES =
  INFORMATION_SCHEMA.TABLES
  LEFT JOIN provider *_TABLES views by table_catalog/table_schema/table_name
```

Provider-specific fields are appended with provider prefixes, such as `dbt_description`, `lookml_ai_context`, or `osi_source_object_id`. This keeps native columns like `table_name` unambiguous while letting providers enrich matching warehouse tables.

Other generic views can start as unions over provider-normalized views until they get their own native information-schema spine. Provider-specific detail remains in the raw provider tables and is reachable through provider-prefixed source object columns.

### `AGENTS.TABLES`

One row per native warehouse table or view from `INFORMATION_SCHEMA.TABLES`, enriched by any provider-normalized `*_TABLES` view that matches the same catalog/schema/table identity.

Suggested columns:

```text
table_catalog
table_schema
table_name
table_type
table_owner
is_transient
clustering_key
row_count
bytes
retention_time
created
last_altered
comment
dbt_description
dbt_source_object_id
dbt_source_path
dbt_materialization
dbt_tags
lookml_description
lookml_ai_context
lookml_source_object_id
osi_description
osi_ai_context
osi_source_object_id
memories_count
warnings_count
```

Provider mappings:

| Source | Mapping |
|---|---|
| `DBT_MODEL` | `schema_name`, `name`, `description`, `materialization`, `file_path`, `tags` |
| `LOOKML_VIEW` | `sql_table_name` when parseable, `name`, `label`, `description`, `ai_context`, `file_path` |
| `OSI_DATASET` | `source_table`, `name`, `description`, `ai_context` |

Memory contribution:

- table-anchored memories increment `memories_count`
- warning-bearing table memories increment `warnings_count`
- an optional future `agent_memories` field can aggregate compact memory summaries

### `AGENTS.COLUMNS`

One row per field/column-like object.

Suggested columns:

```text
table_catalog
table_schema
table_name
column_name
ordinal_position
data_type
is_nullable
display_name
description
ai_context
semantic_type
is_time_dimension
expression
source_provider
source_object_id
memories_count
warnings_count
```

Provider mappings:

| Source | Mapping |
|---|---|
| `DBT_COLUMN` + `DBT_MODEL` | model schema/name, `column_name`, `data_type`, `description` |
| `LOOKML_DIMENSION` | `view_name`, `field_name`, `field_kind`, `type`, `sql`, `description`, `ai_context`, `primary_key` |
| `LOOKML_MEASURE` | `view_name`, `measure_name`, `type`, `sql`, `description`, `ai_context`, `filters` |
| `OSI_FIELD` + `OSI_DATASET` | dataset source table/name, `field_name`, `label`, `description`, `ai_context`, `is_time_dimension`, `expression` |

Memory contribution:

- column-anchored memories attach directly
- unit rules, enum meanings, timezone warnings, and null semantics can show up in memory counts

### `AGENTS.RELATIONSHIPS`

One row per relationship or dependency edge.

Suggested columns:

```text
relationship_name
from_catalog
from_schema
from_table
from_column
to_catalog
to_schema
to_table
to_column
relationship_type
multiplicity
source_provider
source_object_id
memories_count
warnings_count
```

Provider mappings:

| Source | Mapping |
|---|---|
| `DBT_DEPENDENCY` | lineage edge from upstream node to downstream model |
| `OSI_RELATIONSHIP` | explicit semantic relationship with from/to datasets and columns |
| LookML explores | future: join graph from explore definitions once modeled in a table |

Memory contribution:

- relationship-anchored memories attach directly
- fanout warnings and safe-join rules surface during join planning

### `AGENTS.METRICS`

One row per metric or measure-like semantic object.

Suggested columns:

```text
metric_name
display_name
description
ai_context
expression
source_provider
source_object_id
dataset_name
view_name
memories_count
warnings_count
```

Provider mappings:

| Source | Mapping |
|---|---|
| `OSI_METRIC` | metric name, description, ai_context, expression |
| `LOOKML_MEASURE` | measure name, view name, type/sql/filter expression, description, ai_context |
| dbt semantic layer | future provider |

Memory contribution:

- metric-anchored memories attach directly
- calculation caveats, exclusions, date policies, and unit rules show up near metrics

### `AGENTS.ENTITIES`

One row per canonical business entity when a provider contributes entity metadata.

Suggested columns:

```text
entity_id
display_name
description
source_provider
source_object_id
primary_table_schema
primary_table_name
primary_key_columns
memories_count
warnings_count
```

Initial provider mappings may be sparse. OSI entity-like structures, dbt semantic models, or custom providers can populate this later.

Memory contribution:

- entity-anchored memories define identity rules and cross-source mappings
- examples: account is canonical customer, email is not stable identity, subscription is billing relationship not customer

## Example Queries

Column lookup with richer context:

```sql
SELECT
  table_schema,
  table_name,
  column_name,
  data_type,
  description,
  ai_context,
  memories_count,
  warnings_count
FROM AGENTS.COLUMNS
WHERE LOWER(column_name) LIKE '%amount%';
```

Find semantic tables with warning-bearing memories:

```sql
SELECT
  table_schema,
  table_name,
  description,
  source_provider,
  warnings_count
FROM AGENTS.TABLES
WHERE warnings_count > 0;
```

Find metrics with context:

```sql
SELECT
  metric_name,
  description,
  ai_context,
  expression,
  source_provider
FROM AGENTS.METRICS
WHERE LOWER(metric_name) IN ('arr', 'mrr', 'revenue');
```

## Memory Provider Interaction

The views should not own memories. They should consume a memory provider if present.

If `AGENTS.MEMORY` and `AGENTS.MEMORY_ANCHOR` exist:

- `AGENTS.TABLES` can count table-anchored memories.
- `AGENTS.COLUMNS` can count column-anchored memories.
- `AGENTS.RELATIONSHIPS` can count relationship-anchored memories.
- `AGENTS.METRICS` can count metric-anchored memories.
- `AGENTS.ENTITIES` can count entity-anchored memories.

This keeps memory normalized while making the generic views useful for agents that do not know how to join memory tables yet.

## Should Views Be In Core?

Yes eventually, but they can start as a proposal or optional package because they introduce cross-provider semantics.

The current source tables are provider-owned and easy to reason about. Views add a second layer:

```text
source provider tables -> provider-normalized views -> generic context views -> agent queries
```

That layer should have tests that pin:

- row identity rules
- duplicate handling when multiple providers describe the same object
- how descriptions and `ai_context` are selected or combined
- behavior when the memory provider is absent

## Duplicate And Merge Policy

The hard part is not defining view columns; it is merging provider records.

Recommended first version:

- do not aggressively merge objects from different providers
- emit one row per provider object
- preserve `source_provider` and `source_object_id`
- let agents decide which source to trust when duplicates exist

Later versions can add canonicalization if Agents Schema gains stable warehouse object identifiers.

## Resolved Decisions (v1)

- **Warehouse views, refreshed per ingestion** (fail-soft), not CLI-materialized tables.
- **Native objects are the spine.** `TABLES`/`COLUMNS` start from `INFORMATION_SCHEMA` and enrich; they are not provider-only unions.
- **Memory counts are omitted until the memory provider ships its own view.** No reserved-but-zero columns.
- **Measures live in the deferred `METRICS` surface, not `COLUMNS`.** v1 columns are physical/field-like only.
- **dbt, LookML, and OSI all participate in v1** (LookML/OSI `sql_table_name`/`source_table` are parsed into identity).

## Open Questions

- When relationships land, confirm the `REFERENTIAL_CONSTRAINTS` / `KEY_COLUMN_USAGE` shape over a custom view, including how unenforced/OSI relationships are represented when the native constraint views are empty.
- Cross-database coverage: `INFORMATION_SCHEMA` is per-database, so `AGENTS.TABLES`/`COLUMNS` only cover the database holding `AGENTS`. Should multi-database deployments use `SNOWFLAKE.ACCOUNT_USAGE` (account-wide, latent) as an alternate spine?
- Should provider enrichment be prefixed columns (current) or also offer a coalesced single `description`/`ai_context` with a trust order?
