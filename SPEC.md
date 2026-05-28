# Agents Schema

**A standard for communicating metadata to agents in a lakehouse.**

The Agents Schema is to lakehouses what `AGENTS.md` is to code repositories: a well-known location where tools, agents, and humans can discover what data exists, who owns it, and how to use it responsibly. See [README.md](./README.md) for motivation, positioning, and GitHub workflow usage.

## Core: The `AGENTS` Schema

All Agents Schema tables live in a schema named `AGENTS`. The schema name is fixed as `AGENTS`. This schema must be created by whoever administers the lakehouse. Write access should be limited to providers, read access should be granted as broadly as possible. Providers should not place highly sensitive information in the AGENTS schema.

---

## `AGENTS.ROOT`

The single entry point for all metadata. Every provider that contributes metadata registers itself here.

`AGENTS.ROOT` is what makes the Agents Schema self-documenting. A generic consumer should be able to start here, learn which providers have published metadata, and read descriptions of the tables and conventions those providers expose.

```sql
CREATE TABLE AGENTS.ROOT (
  provider    VARCHAR NOT NULL,  -- namespace, e.g. 'fivetran', 'dbt', 'acme_corp'
  key         VARCHAR NOT NULL,  -- provider-defined section identifier
  description TEXT    NOT NULL,  -- markdown text describing this entry
  PRIMARY KEY (provider, key)
);
```

### Columns

| Column | Description |
|---|---|
| `provider` | A short, lowercase identifier for the metadata contributor. Typically a vendor name (`fivetran`, `dbt`) or an internal team name (`acme_data_platform`). Must match the prefix used in any `AGENTS.{PROVIDER}_*` tables contributed by this provider. |
| `key` | A provider-defined identifier, unique within the provider. Treated as an opaque string by the spec. Two conventional shapes are common and can coexist: (1) the unprefixed name of a contributed table (e.g. `connector` for `AGENTS.FIVETRAN_CONNECTOR`), recommended whenever a row documents a specific table, and (2) a flat or slash-separated path used like a filesystem (e.g. `overview`, `conventions`, `skills/refund_workflow`). |
| `description` | Free-form text. May describe the provider, document a specific table, capture conventions, hold a skill, or carry any other context useful to an agent or human reader. Markdown is the natural default since LLMs are common consumers, but the column is plain text and any shape works. |

### What goes in `ROOT`

A row in `AGENTS.ROOT` can hold any text a provider wants discoverable from inside the warehouse. The only hard rule is that `(provider, key)` is unique. Beyond that, providers are free to use rows however they like — for an overview, conventions, per-table notes, skills, query recipes, deprecation notices, or anything else worth publishing alongside the data. Markdown is a natural fit because consumers are often LLMs, but the column is plain text and any shape works.

It is strongly recommended that when a row is meant to document a specific contributed table, its key match the unprefixed table name (so `(fivetran, connector)` documents `AGENTS.FIVETRAN_CONNECTOR`). This isn't enforced, but following the convention keeps consumers — especially LLM agents — from getting confused about whether a row describes a table or is freeform context.

### Example rows

```
provider   key                       description
---------  ------------------------  ------------------------------------------------
fivetran   overview                  # Fivetran\nFivetran syncs data from SaaS sources...
fivetran   conventions               All sync logs are retained 30 days.
fivetran   connector                 One row per Fivetran connector. See AGENTS.FIVETRAN_CONNECTOR.
fivetran   sync_log                  Recent sync events, errors, and warnings.
dbt        overview                  # dbt\nTransformation layer. See AGENTS.DBT_MODEL...
dbt        model                     One row per dbt model with documentation and owner.
acme_corp  skills/refund_workflow    # Refund Workflow\nWhen a user asks about refunds...
acme_corp  skills/etl_failure        # ETL Failure\n1. Check AGENTS.FIVETRAN_SYNC_LOG...
acme_corp  costs                     # Query Costs\nSee AGENTS.ACME_CORP_TABLE_COSTS.
```

---

## Provider-Contributed Tables

Providers may contribute additional tables to the `AGENTS` schema. To prevent name conflicts, all such tables must follow this naming convention:

```
AGENTS.{PROVIDER}_{TABLE_NAME}
```

The `PROVIDER` prefix must exactly match the `provider` value used in `AGENTS.ROOT`. Providers should register themselves in `AGENTS.ROOT` and should add a row per contributed table using the table-reference key shape described above.

**Example:** If `provider = 'acme_corp'`, contributed tables must be named `AGENTS.ACME_CORP_*`.

---

## Well-Known Extensions

Well-known extensions are provider-contributed tables from specific vendors that tools may query directly — without reading `AGENTS.ROOT` first — because their schema is part of this specification. Providers should still register them in `AGENTS.ROOT`, but the schemas here are stable and publicly documented.

This means there are two valid discovery paths:
- generic discovery: start at `AGENTS.ROOT`, read provider descriptions, then inspect the referenced tables
- shortcut discovery: if a tool already knows a well-known extension, it may query those tables directly

The first path is the default and is what makes the Agents Schema self-describing. The second path exists for convenience and interoperability with tools that want to consume a stable schema without first reading provider-written descriptions.

---

## Extension: `fivetran`

The Fivetran extension surfaces metadata from the [Fivetran Platform Connector](https://fivetran.com/docs/logs/fivetran-platform): the connectors ingesting data, the destinations they write to, the structural schema of synced data, and recent sync health.

Agents can use this extension to understand where raw data came from, when it was last updated, and whether any connectors are in a degraded state.

### `AGENTS.FIVETRAN_CONNECTOR`

One row per Fivetran connector (called a "connection" in the Fivetran UI).

```sql
CREATE TABLE AGENTS.FIVETRAN_CONNECTOR (
  connector_id     VARCHAR NOT NULL PRIMARY KEY,
  connector_name   VARCHAR NOT NULL,
  connector_type   VARCHAR NOT NULL,  -- e.g. 'postgres', 'salesforce', 'stripe'
  destination_id   VARCHAR NOT NULL,
  destination_name VARCHAR NOT NULL,
  destination_schema VARCHAR NOT NULL, -- the schema written to in the warehouse
  status           VARCHAR NOT NULL,  -- 'ACTIVE', 'BROKEN', 'PAUSED', 'DELETED'
  sync_frequency   INTEGER,           -- minutes between syncs, NULL if unscheduled
  last_synced_at   TIMESTAMP,
  created_at       TIMESTAMP NOT NULL,
  description      TEXT               -- optional human-written notes
);
```

| Column | Description |
|---|---|
| `connector_id` | Stable Fivetran-assigned identifier. |
| `connector_type` | The source application type. Use this to understand the origin system. |
| `destination_schema` | The schema in the warehouse where this connector writes its tables. Join to `AGENTS.FIVETRAN_TABLE.schema_name` to enumerate tables. |
| `status` | `BROKEN` or `PAUSED` connectors may mean stale data downstream. |
| `last_synced_at` | When the most recent successful sync completed. |

### `AGENTS.FIVETRAN_TABLE`

One row per synced table, across all connectors.

```sql
CREATE TABLE AGENTS.FIVETRAN_TABLE (
  connector_id  VARCHAR NOT NULL,
  schema_name   VARCHAR NOT NULL,  -- warehouse schema (matches destination_schema)
  table_name    VARCHAR NOT NULL,
  enabled       BOOLEAN NOT NULL,  -- whether this table is included in syncs
  row_count     BIGINT,            -- approximate, as of last sync
  last_synced_at TIMESTAMP,
  PRIMARY KEY (connector_id, schema_name, table_name)
);
```

### `AGENTS.FIVETRAN_COLUMN`

One row per synced column.

```sql
CREATE TABLE AGENTS.FIVETRAN_COLUMN (
  connector_id    VARCHAR NOT NULL,
  schema_name     VARCHAR NOT NULL,
  table_name      VARCHAR NOT NULL,
  column_name     VARCHAR NOT NULL,
  data_type       VARCHAR,
  is_primary_key  BOOLEAN NOT NULL DEFAULT FALSE,
  enabled         BOOLEAN NOT NULL,
  PRIMARY KEY (connector_id, schema_name, table_name, column_name)
);
```

### `AGENTS.FIVETRAN_SYNC_LOG`

Recent sync events — errors, warnings, and completions — for connector health monitoring. Agents should query this to understand whether data freshness issues are due to connector failures.

```sql
CREATE TABLE AGENTS.FIVETRAN_SYNC_LOG (
  log_id        VARCHAR NOT NULL PRIMARY KEY,
  connector_id  VARCHAR NOT NULL,
  sync_id       VARCHAR,
  occurred_at   TIMESTAMP NOT NULL,
  event_type    VARCHAR NOT NULL,    -- 'INFO', 'WARNING', 'ERROR', 'SEVERE'
  message       TEXT NOT NULL,
  message_data  VARIANT              -- structured JSON payload for ERROR/SEVERE events
);
```

| Column | Description |
|---|---|
| `event_type` | `WARNING` and `ERROR` entries indicate transient issues; `SEVERE` typically means the connector is broken and requires intervention. |
| `message_data` | JSON blob with structured context. For schema change events, contains `schema_name` and `table_name`. |

Suggested query for agents checking data freshness:

```sql
SELECT connector_name, status, last_synced_at,
       DATEDIFF('hour', last_synced_at, CURRENT_TIMESTAMP) AS hours_since_sync
FROM AGENTS.FIVETRAN_CONNECTOR
WHERE status != 'PAUSED'
ORDER BY hours_since_sync DESC NULLS FIRST;
```

---

## Extension: `dbt`

The dbt extension provides a normalized, queryable representation of the information in dbt's `manifest.json`. It captures the transformation layer: what models exist, how they are documented, and how they depend on each other.

Agents can use this extension to understand what "curated" tables exist (as opposed to raw ingested data), trace column lineage, and find model owners.

### `AGENTS.DBT_MODEL`

One row per dbt model. Corresponds to `nodes` entries in `manifest.json` where `resource_type = 'model'`.

```sql
CREATE TABLE AGENTS.DBT_MODEL (
  unique_id        VARCHAR NOT NULL PRIMARY KEY, -- 'model.<package>.<name>'
  name             VARCHAR NOT NULL,
  package_name     VARCHAR NOT NULL,
  database_name    VARCHAR NOT NULL,  -- warehouse database
  schema_name      VARCHAR NOT NULL,  -- warehouse schema
  materialization  VARCHAR NOT NULL,  -- 'table', 'view', 'incremental', 'ephemeral'
  description      TEXT,              -- from schema.yml
  owner            VARCHAR,           -- from meta.owner or config.meta.owner
  tags             ARRAY,             -- list of string tags
  file_path        VARCHAR NOT NULL,  -- relative path to .sql file
  access           VARCHAR,           -- 'public', 'protected', 'private' (dbt 1.7+)
  contract_enforced BOOLEAN DEFAULT FALSE,
  created_at       TIMESTAMP          -- manifest generation time
);
```

| Column | Description |
|---|---|
| `unique_id` | Globally unique. Use this to join to other dbt extension tables. |
| `materialization` | Ephemeral models have no warehouse object; agents should note this when suggesting queries. |
| `description` | Free-text documentation from `schema.yml`. Often the richest signal about what a model represents. |
| `owner` | Populated from `meta.owner` in `schema.yml`. Useful for routing questions about a model. |
| `access` | dbt's access modifier — `public` models are intended for broad use; `private` models are internal to their package. |

### `AGENTS.DBT_COLUMN`

One row per documented column on a model. Normalized from the `columns` map on each node in `manifest.json`.

```sql
CREATE TABLE AGENTS.DBT_COLUMN (
  model_unique_id  VARCHAR NOT NULL,  -- FK to AGENTS.DBT_MODEL.unique_id
  column_name      VARCHAR NOT NULL,
  data_type        VARCHAR,           -- declared type, may differ from warehouse DDL
  description      TEXT,
  tags             ARRAY,
  meta             VARIANT,           -- arbitrary key-value pairs from schema.yml
  PRIMARY KEY (model_unique_id, column_name)
);
```

### `AGENTS.DBT_DEPENDENCY`

The lineage graph: one row per directed edge in the DAG. Normalized from `parent_map` and `child_map` in `manifest.json`.

```sql
CREATE TABLE AGENTS.DBT_DEPENDENCY (
  upstream_id    VARCHAR NOT NULL,  -- unique_id of the upstream node
  downstream_id  VARCHAR NOT NULL,  -- unique_id of the downstream node
  upstream_type  VARCHAR NOT NULL,  -- 'model', 'source', 'seed', 'snapshot'
  downstream_type VARCHAR NOT NULL,
  PRIMARY KEY (upstream_id, downstream_id)
);
```

To find all models that depend (directly or indirectly) on a source, agents can walk this table recursively using a CTE. Example:

```sql
WITH RECURSIVE lineage AS (
  SELECT downstream_id AS node_id FROM AGENTS.DBT_DEPENDENCY
  WHERE upstream_id = 'source.my_project.raw.account'
  UNION ALL
  SELECT d.downstream_id FROM AGENTS.DBT_DEPENDENCY d
  JOIN lineage l ON d.upstream_id = l.node_id
)
SELECT DISTINCT m.name, m.schema_name, m.description
FROM lineage JOIN AGENTS.DBT_MODEL m ON m.unique_id = lineage.node_id;
```

---

## Conventions and Guidance for Implementors

### Populating the tables

Agents Schema tables are typically populated by:
- **Vendor-run pipelines** that sync provider metadata into the warehouse
- **CI/CD jobs** (e.g. a dbt post-deploy step that parses `manifest.json` and loads `AGENTS.DBT_*`)
- **Platform engineering teams** maintaining custom provider tables

### Staleness

Each extension table should ideally carry a `_synced_at` timestamp in a companion `AGENTS.{PROVIDER}_SYNC_STATUS` table or as a column on the table itself. Agents should check this before drawing conclusions about current state.

### Permissions

- `AGENTS.ROOT` and all extension tables should be readable by any warehouse principal that runs analytical queries.
- Write access should be tightly controlled — only the owning system should insert or update rows.

### Reserved providers

The following provider names are reserved by this specification:

| Provider | Reserved for |
|---|---|
| `fivetran` | Fivetran Platform Connector extension (this spec) |
| `dbt` | dbt manifest extension (this spec) |
| `agents_schema` | Future use by the Agents Schema specification itself |

---

## Summary of All Tables

| Table | Provider | Purpose |
|---|---|---|
| `AGENTS.ROOT` | *(core)* | Registry of all metadata providers and sections |
| `AGENTS.FIVETRAN_CONNECTOR` | fivetran | One row per Fivetran connector |
| `AGENTS.FIVETRAN_TABLE` | fivetran | Synced tables with row counts and freshness |
| `AGENTS.FIVETRAN_COLUMN` | fivetran | Column-level schema for synced tables |
| `AGENTS.FIVETRAN_SYNC_LOG` | fivetran | Recent sync events, errors, and warnings |
| `AGENTS.DBT_MODEL` | dbt | dbt models with documentation, owner, materialization |
| `AGENTS.DBT_COLUMN` | dbt | Per-column documentation for dbt models |
| `AGENTS.DBT_DEPENDENCY` | dbt | DAG edges for upstream/downstream lineage |
