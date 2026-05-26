# Agents Schema

**A standard for communicating metadata to agents in a lakehouse.**

The Agents Schema is to lakehouses what `AGENTS.md` is to code repositories: a well-known location where tools, agents, and humans can discover what data exists, who owns it, and how to use it responsibly.

![Agents Schema overview](assets/agents-schema-overview.png)

---

## Motivation

Agents operating over a lakehouse need context that isn't captured in table schemas alone: what a table is for, who maintains it, what transformations produced it, what it costs to query, and how it relates to other tables. Today this information lives in wikis, Slack threads, and tribal knowledge. The Agents Schema puts it in the warehouse itself, where agents can find it without leaving the query interface.

---

## What This Is For

The Agents Schema is primarily a discovery and orientation layer for agents working from inside a lakehouse or warehouse query surface.

Its main use cases are:
- helping agents discover what data exists, who owns it, and how it should be interpreted
- surfacing operational and semantic context close to the data itself
- providing a standard in-warehouse place for metadata from multiple systems to coexist
- enabling portable agent and tool behavior across warehouses without bespoke integrations for every provider

In practice, this means an agent should be able to connect to a warehouse, inspect the `AGENTS` schema, and quickly answer questions like:
- what curated tables exist versus raw ingested tables?
- which system populated this schema?
- what dbt model or semantic object represents this dataset?
- is this source stale or unhealthy?
- who owns this data product?

Well-known extensions are also a mechanism for tools to discover specific metadata they care about. For example:
- a BI tool could look specifically for dbt model metadata such as `AGENTS.DBT_MODEL` or `AGENTS.DBT_COLUMN`
- an observability tool could look for freshness or lineage metadata from a specific provider
- a generic agent runtime could use `AGENTS.ROOT` to discover which providers are present before deciding what else to query

The point is interoperability at the warehouse boundary: enough standardization that generic agents and downstream tools can discover useful context without direct access to every upstream system.

An important property of the Agents Schema is that it is self-documenting. The schema is meant to describe itself from inside the warehouse:
- `AGENTS.ROOT` tells a reader which providers are present
- the descriptions in `AGENTS.ROOT` explain what provider-contributed tables exist and how to interpret them
- a consumer can discover useful metadata by querying the warehouse alone, without prior vendor-specific assumptions

Well-known extensions are an optimization on top of that default discovery flow, not a replacement for it. A tool may choose to look directly for a stable, well-known table shape such as the dbt extension, but it does not have to. The baseline contract is still that the schema can be explored and understood through `AGENTS.ROOT`.

---

## What This Is Not For

The Agents Schema is not intended to replace specialized systems, source-native metadata APIs, or development-time tooling.

In particular, it is not:
- a full replacement for dbt artifacts, dbt Cloud APIs, or repository-native metadata parsing
- a substitute for source-control-aware tooling that operates on project files
- the canonical execution interface for vendor-specific platforms
- a complete semantic layer, catalog, or observability product by itself
- a requirement that every tool consume metadata from the warehouse instead of from primary sources

Specialized tools should still build their own context when they need deeper, fresher, or source-native representations.

For example:
- a dbt MCP server meant to help coding agents work on a dbt repository should build its context from the repository itself: model SQL files, YAML properties files, macros, `dbt_project.yml`, and dbt artifacts
- that server should not treat the `AGENTS` schema as its primary source of truth for authoring, refactoring, or validating dbt code
- similarly, a catalog, lineage engine, or observability platform may ingest the Agents Schema, but will often maintain a richer internal model built from APIs, repository scans, logs, or event streams

The Agents Schema is therefore best understood as:
- a shared, queryable metadata surface inside the lakehouse
- a lowest-common-denominator interoperability layer
- a convenient place for agents and tools to discover context when working from the data plane

It is not:
- the only metadata surface in the ecosystem
- the deepest possible representation of any provider's semantics
- a reason to stop building specialized tools with source-native context models

---

## Design Boundary

The boundary is:
- if the consumer starts from the warehouse and needs context about data that already exists there, the Agents Schema is a good fit
- if the consumer starts from a source system or codebase and needs full-fidelity authoring or operational context, it should usually use that system's native artifacts and APIs directly

This is especially important for coding and development workflows. A tool helping an agent edit a dbt repository should use dbt's source files and artifacts directly. A tool helping an agent understand a warehouse it can query should be able to benefit from the Agents Schema.

---

## Comparison to Related Concepts

### Compared to `AGENTS.md`

The analogy to `AGENTS.md` is useful, but the setting is different.

- `AGENTS.md` is for code repositories; the Agents Schema is for warehouses and lakehouses
- `AGENTS.md` is typically curated by developers in a repo; the Agents Schema is expected to be written to by multiple providers that share the same warehouse
- `AGENTS.ROOT.description` is intentionally unstructured markdown, similar to `AGENTS.md`
- beyond `AGENTS.ROOT`, the rest of the Agents Schema will often be more structured, because provider-contributed tables are meant to support machine-readable discovery and joins

### Compared to `information_schema`

The closest existing database analogy is `information_schema`.

- both are meant to be discoverable from inside the database itself
- the Agents Schema is self-documenting through `AGENTS.ROOT`, in the same spirit that `information_schema` exposes metadata from within the system
- the main difference is extensibility: `information_schema` is a strong idea, but it is largely fixed by the warehouse provider and not designed as a shared extension surface for many metadata producers
- you can think of `information_schema` as a pre-existing metadata surface from a single provider, while the Agents Schema allows many providers to effectively publish and share their own `information_schema`-like context in one place

### Compared to MCP Servers

MCP servers and the Agents Schema solve related but different problems.

- the Agents Schema does not require separate authentication or a separate service boundary; it relies on the database access that providers and consumers already share
- its scope is narrower: it provides context, but it is not an action interface
- an MCP server can expose tools that take action, orchestrate workflows, or wrap external systems; the Agents Schema only publishes metadata inside the warehouse
- specialized MCP servers are likely to be common consumers of the Agents Schema
- those servers may cache metadata from the Agents Schema, or special-case known providers and well-known extensions when they want a richer or faster consumer experience

## Core: The `AGENTS` Schema

All Agents Schema tables live in a schema named `AGENTS`. The schema name is fixed as `AGENTS`. This schema must be created by whoever administers the lakehouse. Write access should be limited to providers, read access should be granted as broadly as possible. Providers should not place highly sensitive information in the AGENTS schema.

---

## `AGENTS.ROOT`

The single entry point for all metadata. Every provider that contributes metadata registers itself here.

`AGENTS.ROOT` is what makes the Agents Schema self-documenting. A generic consumer should be able to start here, learn which providers have published metadata, and read descriptions of the tables and conventions those providers expose.

```sql
CREATE TABLE AGENTS.ROOT (
  provider    VARCHAR NOT NULL,  -- namespace, e.g. 'dbt', 'acme_corp'
  key         VARCHAR NOT NULL,  -- provider-defined section identifier
  description TEXT    NOT NULL,  -- markdown text describing this entry
  PRIMARY KEY (provider, key)
);
```

### Columns

| Column | Description |
|---|---|
| `provider` | A short, lowercase identifier for the metadata contributor. Typically a vendor name (`dbt`) or an internal team name (`acme_data_platform`). Must match the prefix used in any `AGENTS.{PROVIDER}_*` tables contributed by this provider. |
| `key` | A provider-defined identifier, unique within the provider. Treated as an opaque string by the spec. Two conventional shapes are common and can coexist: (1) the unprefixed name of a contributed table (e.g. `model` for `AGENTS.DBT_MODEL`), recommended whenever a row documents a specific table, and (2) a flat or slash-separated path used like a filesystem (e.g. `overview`, `conventions`, `skills/refund_workflow`). |
| `description` | Free-form text. May describe the provider, document a specific table, capture conventions, hold a skill, or carry any other context useful to an agent or human reader. Markdown is the natural default since LLMs are common consumers, but the column is plain text and any shape works. |

### What goes in `ROOT`

A row in `AGENTS.ROOT` can hold any text a provider wants discoverable from inside the warehouse. The only hard rule is that `(provider, key)` is unique. Beyond that, providers are free to use rows however they like — for an overview, conventions, per-table notes, skills, query recipes, deprecation notices, or anything else worth publishing alongside the data. Markdown is a natural fit because consumers are often LLMs, but the column is plain text and any shape works.

It is strongly recommended that when a row is meant to document a specific contributed table, its key match the unprefixed table name (so `(dbt, model)` documents `AGENTS.DBT_MODEL`). This isn't enforced, but following the convention keeps consumers — especially LLM agents — from getting confused about whether a row describes a table or is freeform context.

### Example rows

```
provider   key                       description
---------  ------------------------  ------------------------------------------------
dbt        overview                  # dbt\nTransformation layer. See AGENTS.DBT_MODEL...
dbt        model                     One row per dbt model with documentation and owner.
acme_corp  skills/refund_workflow    # Refund Workflow\nWhen a user asks about refunds...
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
| `dbt` | dbt manifest extension (this spec) |
| `agents_schema` | Future use by the Agents Schema specification itself |

---

## Summary of All Tables

| Table | Provider | Purpose |
|---|---|---|
| `AGENTS.ROOT` | *(core)* | Registry of all metadata providers and sections |
| `AGENTS.DBT_MODEL` | dbt | dbt models with documentation, owner, materialization |
| `AGENTS.DBT_COLUMN` | dbt | Per-column documentation for dbt models |
| `AGENTS.DBT_DEPENDENCY` | dbt | DAG edges for upstream/downstream lineage |
