# Agents Schema

**A standard warehouse schema for metadata that agents need in order to work with data.**

Agents Schema gives agents a predictable place to find context about warehouse data: what models exist, what fields mean, how semantic-layer objects are defined, and how those objects relate to each other. See [README.md](./README.md) for motivation, positioning, and GitHub workflow usage.

This document describes the logical warehouse tables produced by this repository's current ingestion workflows. The SQL below is written in Snowflake form as a readable reference for the schema contract. See [README.md](./README.md#warehouse-credentials) for supported destination setup.

## Core: The `AGENTS` Schema

All Agents Schema tables live in a schema named `AGENTS`. The current writer creates the schema if it does not already exist.

The implementation writes unquoted identifiers, so Snowflake stores table and column names in uppercase. The Python package defines them in lowercase internally, but the delivered warehouse objects are the uppercase `AGENTS.*` tables shown here.

### Supported Types

| Internal kind | Snowflake type | Notes |
|---|---|---|
| `varchar` | `VARCHAR` | String values. |
| `text` | `TEXT` | Longer free-form text. |
| `boolean` | `BOOLEAN` | Boolean values. |
| `array` | `VARIANT` | Inserted as JSON via `PARSE_JSON`. |

---

## `AGENTS.ROOT`

`AGENTS.ROOT` is the intended provider registry for the Agents Schema. It gives generic consumers one place to discover which providers have published metadata, how to use their tables, and which warehouse-delivered skills are available.

The current dbt, LookML, OSI, and skills ingestion workflows upsert their own provider rows into `AGENTS.ROOT` and write the source-specific tables documented below. Each workflow preserves `ROOT` rows from other providers.

```sql
CREATE TABLE AGENTS.ROOT (
  provider    VARCHAR NOT NULL,
  key         VARCHAR NOT NULL,
  content     TEXT NOT NULL,
  PRIMARY KEY (provider, key)
);
```

| Column | Description |
|---|---|
| `provider` | A short, lowercase identifier for the metadata contributor, such as `dbt`, `lookml`, `osi`, `skills`, `fivetran`, or `user`. |
| `key` | Provider-defined identifier, unique within the provider. For table documentation, the recommended convention is the unprefixed table name, such as `model` for `AGENTS.DBT_MODEL`. |
| `content` | Free-form context about the provider, table, convention, skill, or anything else the provider wants discoverable. |

### What goes in `ROOT`

A row in `AGENTS.ROOT` can hold any text a provider wants discoverable from inside the warehouse. The only hard rule is that `(provider, key)` is unique. Beyond that, providers are free to use rows however they like: for an overview, conventions, per-table notes, skills, query recipes, deprecation notices, or anything else worth publishing alongside the data. Markdown is a natural fit because consumers are often LLMs, but the column is plain text and any shape works.

It is strongly recommended that when a row is meant to document a specific contributed table, its key match the unprefixed table name. For example, `(dbt, model)` documents `AGENTS.DBT_MODEL`, and `(lookml, explore)` documents `AGENTS.LOOKML_EXPLORE`. This is not enforced, but following the convention keeps consumers, especially LLM agents, from getting confused about whether a row describes a table or is freeform context.

### Skill rows in `ROOT`

Skills are agent-readable instructions delivered through `AGENTS.ROOT`. A skill row uses the convention:

```
provider = <publisher>
key      = skill/<name>
content  = markdown skill body
```

The skill body may include YAML frontmatter. The only standard frontmatter field in this version is `uses`, which declares the additive set of schemas and tables the skill may use:

```markdown
---
uses:
  schemas:
    - QUICKSTART_FINANCE
  tables:
    - QUICKSTART_FINANCE.ARR_SNAPSHOT
---

# Revenue Skill

Use this skill when answering ARR, MRR, recurring revenue, or revenue trend questions.
```

`uses.schemas` means the skill may use all tables in that schema. `uses.tables` entries must be schema-qualified table names. The lists are additive and do not express exclusions. Consumers can read skills with:

```sql
SELECT provider, key, content
FROM AGENTS.ROOT
WHERE key LIKE 'skill/%'
ORDER BY provider, key;
```

### Example rows

```
provider   key                       content
---------  ------------------------  ------------------------------------------------
dbt        overview                  # dbt\nTransformation metadata from manifest.json.
dbt        model                     One row per dbt model. See AGENTS.DBT_MODEL.
dbt        dependency                Direct dbt DAG edges. See AGENTS.DBT_DEPENDENCY.
lookml     overview                  # LookML\nSemantic metadata parsed from LookML files.
lookml     view                      One row per LookML view. See AGENTS.LOOKML_VIEW.
lookml     explore                   One row per LookML explore. See AGENTS.LOOKML_EXPLORE.
osi        overview                  # OSI\nOpen Semantic Interchange metadata.
osi        dataset                   One row per OSI dataset. See AGENTS.OSI_DATASET.
osi        metric                    One row per OSI metric. See AGENTS.OSI_METRIC.
skills     overview                  # Skills\nWarehouse-delivered agent skills...
skills     skill_use                 Optional parsed skill data-use declarations.
acme_corp  skill/refund_workflow     # Refund Workflow\nWhen a user asks about refunds...
acme_corp  costs                     # Query Costs\nUse this before running expensive joins.
```

---

## Delivered Source Tables

The current package delivers one table family per metadata source:

| Source | Tables |
|---|---|
| dbt | `AGENTS.DBT_MODEL`, `AGENTS.DBT_COLUMN`, `AGENTS.DBT_DEPENDENCY` |
| LookML | `AGENTS.LOOKML_VIEW`, `AGENTS.LOOKML_DIMENSION`, `AGENTS.LOOKML_MEASURE`, `AGENTS.LOOKML_EXPLORE` |
| OSI | `AGENTS.OSI_DATASET`, `AGENTS.OSI_FIELD`, `AGENTS.OSI_METRIC`, `AGENTS.OSI_RELATIONSHIP` |
| Skills | `AGENTS.SKILL_USE` |

Each ingestion replaces its own table family with `CREATE OR REPLACE TABLE` and then inserts the rows parsed from the source metadata.

---

## Source: Skills

The skills ingestion reads markdown files and publishes each file as a skill row in `AGENTS.ROOT`. It also parses compliant `uses` frontmatter into `AGENTS.SKILL_USE` so consumers can quickly find which skills may use a schema or table.

Skill rows are stored in `AGENTS.ROOT` under the publisher passed to the CLI. The skills CLI defaults to `--provider user`. For example, `skills/revenue/arr.md` without an explicit provider is published as `(user, skill/revenue/arr)`, while the same file with `--provider fivetran` is published as `(fivetran, skill/revenue/arr)`.

### `AGENTS.SKILL_USE`

One row per parsed skill use declaration. Missing frontmatter produces no rows. Malformed `uses` frontmatter should not block publication of the skill markdown to `AGENTS.ROOT`, but should be skipped for `AGENTS.SKILL_USE`.

```sql
CREATE OR REPLACE TABLE AGENTS.SKILL_USE (
  provider   VARCHAR NOT NULL,
  skill_key  VARCHAR NOT NULL,
  use_kind   VARCHAR NOT NULL,
  object_ref VARCHAR NOT NULL,
  PRIMARY KEY (provider, skill_key, use_kind, object_ref)
);
```

| Column | Description |
|---|---|
| `provider` | Publisher used for the corresponding `AGENTS.ROOT` skill row. |
| `skill_key` | `AGENTS.ROOT.key` value for the skill, such as `skill/revenue/arr`. |
| `use_kind` | Either `schema` or `table`. |
| `object_ref` | Schema name for `schema`, or schema-qualified table name for `table`. |

---

## Source: dbt

The dbt ingestion reads a compiled dbt `manifest.json` and writes normalized model, column, and dependency tables. It captures the transformation layer that is useful from the warehouse: what models exist, how they are documented, and which upstream nodes they depend on.

Agents can use this extension to understand what curated tables exist, inspect column documentation, and trace direct lineage from dbt's dependency graph.

### `AGENTS.DBT_MODEL`

One row per dbt model from `manifest.json` entries where `resource_type = 'model'`.

```sql
CREATE OR REPLACE TABLE AGENTS.DBT_MODEL (
  unique_id       VARCHAR NOT NULL,
  name            VARCHAR NOT NULL,
  schema_name     VARCHAR,
  materialization VARCHAR,
  description     TEXT,
  file_path       VARCHAR,
  tags            VARIANT,
  PRIMARY KEY (unique_id)
);
```

| Column | Source field |
|---|---|
| `unique_id` | Manifest node key, for example `model.package.model_name`. |
| `name` | `node.name`. |
| `schema_name` | `node.schema`. |
| `materialization` | `node.config.materialized`. |
| `description` | `node.description`; empty string when missing. |
| `file_path` | `node.original_file_path`. |
| `tags` | `node.tags`, serialized as JSON into a Snowflake `VARIANT`. |

### `AGENTS.DBT_COLUMN`

One row per documented column on a dbt model.

```sql
CREATE OR REPLACE TABLE AGENTS.DBT_COLUMN (
  model_id    VARCHAR NOT NULL,
  column_name VARCHAR NOT NULL,
  data_type   VARCHAR,
  description TEXT,
  PRIMARY KEY (model_id, column_name)
);
```

| Column | Source field |
|---|---|
| `model_id` | Parent model `unique_id`. |
| `column_name` | Key from `node.columns`. |
| `data_type` | `column.data_type`; empty string when missing. |
| `description` | `column.description`; empty string when missing. |

### `AGENTS.DBT_DEPENDENCY`

One row per direct dependency from a dbt model's `depends_on.nodes`.

```sql
CREATE OR REPLACE TABLE AGENTS.DBT_DEPENDENCY (
  upstream_id     VARCHAR NOT NULL,
  downstream_id   VARCHAR NOT NULL,
  upstream_type   VARCHAR,
  downstream_type VARCHAR,
  PRIMARY KEY (upstream_id, downstream_id)
);
```

| Column | Source field |
|---|---|
| `upstream_id` | Dependency unique ID from `node.depends_on.nodes`. |
| `downstream_id` | Current model `unique_id`. |
| `upstream_type` | Prefix before the first `.` in `upstream_id`, or `unknown` when no prefix exists. |
| `downstream_type` | Always `model` in the current dbt ingestion. |

To find all models that depend directly or indirectly on a source, agents can walk this table recursively:

```sql
WITH RECURSIVE lineage AS (
  SELECT downstream_id AS node_id
  FROM AGENTS.DBT_DEPENDENCY
  WHERE upstream_id = 'source.my_project.raw.account'

  UNION ALL

  SELECT d.downstream_id
  FROM AGENTS.DBT_DEPENDENCY d
  JOIN lineage l ON d.upstream_id = l.node_id
)
SELECT DISTINCT m.name, m.schema_name, m.description
FROM lineage
JOIN AGENTS.DBT_MODEL m ON m.unique_id = lineage.node_id;
```

---

## Source: LookML

The LookML ingestion scans `*.lkml` files and writes normalized view, dimension, measure, and explore tables. It parses top-level `view` and `explore` blocks, plus `dimension`, `dimension_group`, and `measure` blocks inside views.

Agents can use this extension to understand the BI and semantic surface exposed through Looker: which explores exist, which views back them, what fields are available, and which fields include human-authored `description` or `ai_context`.

### `AGENTS.LOOKML_VIEW`

One row per LookML `view` block.

```sql
CREATE OR REPLACE TABLE AGENTS.LOOKML_VIEW (
  name           VARCHAR NOT NULL,
  sql_table_name VARCHAR,
  label          VARCHAR,
  description    TEXT,
  ai_context     TEXT,
  file_path      VARCHAR,
  PRIMARY KEY (name)
);
```

| Column | Source field |
|---|---|
| `name` | View block name. |
| `sql_table_name` | View `sql_table_name`. |
| `label` | View `label`. |
| `description` | View `description`. |
| `ai_context` | View `ai_context`. |
| `file_path` | Relative path to the `.lkml` file from the configured LookML directory. |

### `AGENTS.LOOKML_DIMENSION`

One row per LookML `dimension` or `dimension_group` block inside a view.

```sql
CREATE OR REPLACE TABLE AGENTS.LOOKML_DIMENSION (
  view_name   VARCHAR NOT NULL,
  field_name  VARCHAR NOT NULL,
  field_kind  VARCHAR NOT NULL,
  type        VARCHAR,
  sql         TEXT,
  description TEXT,
  ai_context  TEXT,
  primary_key BOOLEAN,
  PRIMARY KEY (view_name, field_name)
);
```

| Column | Source field |
|---|---|
| `view_name` | Parent view name. |
| `field_name` | Dimension or dimension group block name. |
| `field_kind` | Either `dimension` or `dimension_group`. |
| `type` | Field `type`. |
| `sql` | Field `sql`, with LookML `;;` terminator removed. |
| `description` | Field `description`. |
| `ai_context` | Field `ai_context`. |
| `primary_key` | Field `primary_key`, parsed as a boolean. |

### `AGENTS.LOOKML_MEASURE`

One row per LookML `measure` block inside a view.

```sql
CREATE OR REPLACE TABLE AGENTS.LOOKML_MEASURE (
  view_name    VARCHAR NOT NULL,
  measure_name VARCHAR NOT NULL,
  type         VARCHAR,
  sql          TEXT,
  description  TEXT,
  ai_context   TEXT,
  filters      TEXT,
  PRIMARY KEY (view_name, measure_name)
);
```

| Column | Source field |
|---|---|
| `view_name` | Parent view name. |
| `measure_name` | Measure block name. |
| `type` | Measure `type`. |
| `sql` | Measure `sql`, with LookML `;;` terminator removed. |
| `description` | Measure `description`. |
| `ai_context` | Measure `ai_context`. |
| `filters` | Measure `filters`, stored as text by the current parser. |

### `AGENTS.LOOKML_EXPLORE`

One row per LookML `explore` block.

```sql
CREATE OR REPLACE TABLE AGENTS.LOOKML_EXPLORE (
  name        VARCHAR NOT NULL,
  from_view   VARCHAR,
  label       VARCHAR,
  description TEXT,
  ai_context  TEXT,
  file_path   VARCHAR,
  PRIMARY KEY (name)
);
```

| Column | Source field |
|---|---|
| `name` | Explore block name. |
| `from_view` | Explore `from`; defaults to the explore name when `from` is missing. |
| `label` | Explore `label`. |
| `description` | Explore `description`. |
| `ai_context` | Explore `ai_context`. |
| `file_path` | Relative path to the `.lkml` file from the configured LookML directory. |

---

## Source: OSI

The OSI ingestion scans direct `*.osi.yaml` files in the configured OSI directory and reads each file's top-level `semantic_model` object. It writes normalized dataset, field, metric, and relationship tables.

Agents can use this extension to understand an Open Semantic Interchange model from inside the warehouse: which datasets exist, which fields and metrics are documented, and how datasets relate to each other.

### `AGENTS.OSI_DATASET`

One row per OSI dataset from `semantic_model.datasets`.

```sql
CREATE OR REPLACE TABLE AGENTS.OSI_DATASET (
  name         VARCHAR NOT NULL,
  source_table VARCHAR NOT NULL,
  primary_key  VARIANT,
  description  TEXT,
  ai_context   TEXT,
  PRIMARY KEY (name)
);
```

| Column | Source field |
|---|---|
| `name` | Dataset `name`. |
| `source_table` | Dataset `source`; empty string when missing. |
| `primary_key` | Dataset `primary_key`, serialized as JSON into a Snowflake `VARIANT`. |
| `description` | Dataset `description`; empty string when missing. |
| `ai_context` | Dataset `ai_context`; empty string when missing. |

### `AGENTS.OSI_FIELD`

One row per field from each OSI dataset.

```sql
CREATE OR REPLACE TABLE AGENTS.OSI_FIELD (
  dataset_name      VARCHAR NOT NULL,
  field_name        VARCHAR NOT NULL,
  label             VARCHAR,
  description       TEXT,
  ai_context        TEXT,
  is_time_dimension BOOLEAN,
  expression        TEXT,
  PRIMARY KEY (dataset_name, field_name)
);
```

| Column | Source field |
|---|---|
| `dataset_name` | Parent dataset `name`. |
| `field_name` | Field `name`. |
| `label` | Field `label`. |
| `description` | Field `description`; empty string when missing. |
| `ai_context` | Field `ai_context`; empty string when missing. |
| `is_time_dimension` | `true` when `field.dimension.is_time` is truthy; otherwise `false`. |
| `expression` | First expression from `field.expression.dialects[].expression`, when present. |

### `AGENTS.OSI_METRIC`

One row per OSI metric from `semantic_model.metrics`.

```sql
CREATE OR REPLACE TABLE AGENTS.OSI_METRIC (
  name        VARCHAR NOT NULL,
  description TEXT,
  ai_context  TEXT,
  expression  TEXT,
  PRIMARY KEY (name)
);
```

| Column | Source field |
|---|---|
| `name` | Metric `name`. |
| `description` | Metric `description`; empty string when missing. |
| `ai_context` | Metric `ai_context`; empty string when missing. |
| `expression` | First expression from `metric.expression.dialects[].expression`, when present. |

### `AGENTS.OSI_RELATIONSHIP`

One row per OSI relationship from `semantic_model.relationships`.

```sql
CREATE OR REPLACE TABLE AGENTS.OSI_RELATIONSHIP (
  name         VARCHAR NOT NULL,
  from_dataset VARCHAR NOT NULL,
  to_dataset   VARCHAR NOT NULL,
  from_columns VARIANT NOT NULL,
  to_columns   VARIANT NOT NULL,
  PRIMARY KEY (name)
);
```

| Column | Source field |
|---|---|
| `name` | Relationship `name`. |
| `from_dataset` | Relationship `from`. |
| `to_dataset` | Relationship `to`. |
| `from_columns` | Relationship `from_columns`, serialized as JSON into a Snowflake `VARIANT`. |
| `to_columns` | Relationship `to_columns`, serialized as JSON into a Snowflake `VARIANT`. |

---

## Cross-Source Queries

One of the most valuable things agents can do is join across delivered source tables. For example, an agent can discover a LookML view, identify the warehouse relation it references, and compare that to dbt model names and schemas:

```sql
SELECT
  v.name AS lookml_view,
  v.sql_table_name,
  m.unique_id AS dbt_model_id,
  m.name AS dbt_model,
  m.schema_name,
  m.description AS dbt_description
FROM AGENTS.LOOKML_VIEW v
LEFT JOIN AGENTS.DBT_MODEL m
  ON LOWER(v.sql_table_name) LIKE '%' || LOWER(m.schema_name) || '.' || LOWER(m.name) || '%';
```

That join is intentionally heuristic because LookML `sql_table_name` is free-form LookML text. It is still useful as an orientation query for agents trying to connect BI-facing objects back to modeled warehouse tables.

---

## Conventions and Guidance for Implementors

### Populating the Tables

Agents Schema tables can be populated in several ways:
- **Vendor-run pipelines** that sync provider metadata into the warehouse
- **CI/CD jobs** that parse source artifacts and load `AGENTS.*` tables after project changes
- **Scheduled workflows** that periodically refresh metadata from source systems or repositories
- **Platform engineering jobs** that maintain user-published provider tables for internal metadata, skills, query recipes, or operational context

This repository currently provides source-specific GitHub reusable workflows for dbt, LookML, OSI, and skills ingestion. Those workflows are one implementation path, not a requirement that all Agents Schema metadata be produced through GitHub Actions.

Each source ingestion owns its table family and may replace those tables on each run. Consumers should treat these tables as generated metadata, not as hand-edited state.

### Permissions

- `AGENTS.ROOT` and all delivered source tables should be readable by any warehouse principal that runs analytical or agentic queries.
- Write access should be tightly controlled and limited to the workflows or service principals that publish Agents Schema metadata.

### Provider Names

The following provider names are reserved:

| Provider | Purpose |
|---|---|
| `dbt` | dbt metadata in `AGENTS.DBT_*` |
| `lookml` | LookML metadata in `AGENTS.LOOKML_*` |
| `osi` | OSI metadata in `AGENTS.OSI_*` |
| `skills` | Skills extension metadata in `AGENTS.SKILL_USE` |
| `user` | User-published skills, metadata, query recipes, or operational context |

---

## Summary of Current Tables

| Table | Source | Purpose |
|---|---|---|
| `AGENTS.ROOT` | core | Provider registry and skill delivery surface upserted by source workflows |
| `AGENTS.SKILL_USE` | skills | Parsed skill schema and table use declarations |
| `AGENTS.DBT_MODEL` | dbt | dbt models with schema, materialization, documentation, path, and tags |
| `AGENTS.DBT_COLUMN` | dbt | Documented dbt model columns |
| `AGENTS.DBT_DEPENDENCY` | dbt | Direct dbt dependency edges |
| `AGENTS.LOOKML_VIEW` | LookML | LookML views and view-level context |
| `AGENTS.LOOKML_DIMENSION` | LookML | LookML dimensions and dimension groups |
| `AGENTS.LOOKML_MEASURE` | LookML | LookML measures |
| `AGENTS.LOOKML_EXPLORE` | LookML | LookML explores |
| `AGENTS.OSI_DATASET` | OSI | OSI datasets and dataset-level context |
| `AGENTS.OSI_FIELD` | OSI | OSI dataset fields |
| `AGENTS.OSI_METRIC` | OSI | OSI metrics |
| `AGENTS.OSI_RELATIONSHIP` | OSI | OSI relationships between datasets |
