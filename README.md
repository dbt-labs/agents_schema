# Agents Schema

Agents need context to answer questions about warehouse data. Agents Schema puts
that context in the warehouse itself, in a standard `AGENTS` schema, so agents
can query metadata next to the data they are reasoning over. See
[Why Agents Schema](#why-agents-schema) for more on the idea behind it and
[SPEC.md](./SPEC.md) for the schema contract.

This repository provides GitHub workflows that ingest source metadata from
your repository and publish it into `AGENTS`.

![Agents Schema overview](assets/agents-schema-overview.png)

Run one of the workflows below to populate the `AGENTS` schema from a source
you already have. Once it's populated, anything that already queries your
warehouse can read those tables as ordinary SQL, including Cursor, Claude
Code, notebooks, and internal agents. The fastest path is usually dbt: if your
repo already produces `target/manifest.json`, the workflow only needs the dbt
project path and your warehouse credentials.

After the first run, your warehouse has queryable metadata tables such as
`AGENTS.DBT_MODEL` and `AGENTS.DBT_COLUMN`. Agents can use those tables to
understand which models exist, how they are documented, how they relate to the
warehouse, and what context is available before writing or explaining queries.

## Contents

- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
- [Guides](#guides)
  - [Sync dbt](#sync-dbt)
  - [Sync Looker](#sync-looker)
  - [Sync Multiple Sources](#sync-multiple-sources)
- [Why Agents Schema](#why-agents-schema)
  - [How it works](#how-it-works)
- [Reference](#reference)
  - [CLI](#cli)
  - [Versioning](#versioning)
  - [Specification](#specification)

## Getting Started

There are two supported metadata providers. Pick one of them to get started quickly.
- [dbt](#sync-dbt)
- [Looker](#sync-looker)

### Prerequisites

Create one required GitHub Actions secret in the repository that calls these
workflows:

```text
WAREHOUSE_CREDENTIALS
```

Snowflake is the only supported destination today, with more destination
support coming soon. We recommend key-pair authentication:

**Key-pair auth:**

```yaml
type: snowflake
account: abc123
user: AGENTS_SCHEMA_BOT
warehouse: COMPUTE_WH
database: ANALYTICS
role: TRANSFORMER
private_key_pem: |
  -----BEGIN ENCRYPTED PRIVATE KEY-----
  MIIEvQIBADANBgkqh...
  -----END ENCRYPTED PRIVATE KEY-----
private_key_passphrase: your-passphrase   # only if the key is encrypted
```

`role` is optional. An unencrypted key uses `-----BEGIN PRIVATE KEY-----` /
`-----END PRIVATE KEY-----` markers (without `ENCRYPTED`) and omits
`private_key_passphrase`. JSON works with the same field names.

The destination object configures the warehouse and connection. The schema
name is always `AGENTS`. The destination user needs permission to create or
replace tables in that schema.

`WAREHOUSE_CREDENTIALS` is only the destination for writing `AGENTS`. If the
workflow needs to run dbt, the dbt adapter is selected from the dbt profile, not
from these destination credentials.

## Guides

- [dbt Setup Guide](dbt-setup.md)
- [Looker Setup Guide](looker-setup.md)

## Why Agents Schema

Agents operating over a warehouse need context that is not captured in table
schemas alone: what a table is for, who maintains it, what transformations
produced it, what it costs to query, and how it relates to other tables. Today
this information often lives in wikis, Slack threads, dashboards, and tribal
knowledge. Agents Schema puts it in the warehouse itself, where agents can find
it without leaving the query interface.

Agents Schema is a discovery layer for agents that already query your
warehouse. It gives them a standard place to ask: what curated tables exist,
which system published the metadata, what dbt model or LookML object backs a
dataset, whether a source is stale, and who owns a data product.

The schema is self-documenting. `AGENTS.ROOT` tells consumers which providers
are present and explains what provider-contributed tables mean. Consumers can
start there for generic discovery, or query well-known extension tables directly
when they already know the shape they need.

Agents Schema is not a replacement for specialized systems, source-native
metadata APIs, or development-time tooling. A dbt MCP server helping an agent
edit a dbt repository should still use dbt source files and artifacts directly.
Agents Schema is the shared, queryable metadata surface for consumers that start
from the warehouse and need context about data that already exists there.

It is closest in spirit to `information_schema`, but extensible across many
providers. Compared with MCP servers, Agents Schema is narrower: it publishes
context inside the warehouse, while MCP servers can expose tools, actions, and
source-specific workflows.

### How it works

1. A workflow in your repository invokes one of this repo's workflows.
2. The workflow checks out your repository and reads source metadata such as
   dbt artifacts or LookML files.
3. The workflow runs the `agents-schema` CLI at the pinned release tag.
4. The CLI writes normalized metadata into the warehouse under the `AGENTS`
   schema.
5. Agents and downstream tools query `AGENTS` for context close to the data
   itself.

## Reference

### CLI

The GitHub Actions call the CLI with explicit source arguments:

```bash
agents-schema dbt --project-dir dbt_project
agents-schema looker --lookml-dir lookml
```

The CLI reads warehouse credentials from `WAREHOUSE_CREDENTIALS`.

### Versioning

Release tags version the whole repository: reusable workflows, actions, CLI
source, examples, README, and spec.

Pin exact tags in your workflows:

```yaml
uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.1
```

To upgrade, change only the tag:

```diff
- uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.1
+ uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.2
```

### Specification

The full schema contract is in [SPEC.md](./SPEC.md). Keep schema definitions and
compatibility rules there; keep this README focused on installation and
source-specific GitHub workflow usage.
