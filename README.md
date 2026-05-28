# Agents Schema

Agents Schema is a standard, in-warehouse metadata surface for agents. It gives
tools, agents, and humans a well-known place to discover what data exists, who
owns it, what produced it, and how it should be used.

![Agents Schema overview](assets/agents-schema-overview.png)

The first officially supported ingestion sources are:

- dbt: reads `target/manifest.json` and writes `AGENTS.DBT_*` tables.
- Looker: reads `*.lkml` files and writes `AGENTS.LOOKML_*` tables.

This repository provides GitHub reusable workflows that ingest source metadata
from a customer's repository and publish it into the warehouse. After the
`AGENTS` schema is populated, agents can consume it directly with SQL, through
skills, through specialized MCP servers, or through any other tool that can read
from the warehouse.

The full schema contract is defined in [SPEC.md](./SPEC.md).

## Motivation

Agents operating over a warehouse need context that is not captured in table
schemas alone: what a table is for, who maintains it, what transformations
produced it, what it costs to query, and how it relates to other tables. Today
this information often lives in wikis, Slack threads, dashboards, and tribal
knowledge. Agents Schema puts it in the warehouse itself, where agents can find
it without leaving the query interface.

## Contents

- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
  - [Warehouse Credentials](#warehouse-credentials)
- [Sync dbt](#sync-dbt)
  - [Use an Existing Manifest](#use-an-existing-manifest)
  - [Generate a Manifest with dbt Parse](#generate-a-manifest-with-dbt-parse)
  - [Run a Custom dbt Parse Command](#run-a-custom-dbt-parse-command)
- [Sync Looker](#sync-looker)
- [Sync Multiple Sources](#sync-multiple-sources)
- [Reference](#reference)
  - [CLI](#cli)
  - [Versioning](#versioning)
  - [Specification](#specification)

## How It Works

The ingestion flow is:

1. A customer repository calls one of this repo's reusable GitHub workflows.
2. The workflow checks out the customer repository and reads source metadata,
   such as dbt artifacts or LookML files.
3. The workflow runs the `agents-schema` CLI from this repository at the pinned
   release tag.
4. The CLI writes normalized metadata into the warehouse under the fixed
   `AGENTS` schema.
5. Agents and downstream tools query `AGENTS` to discover context close to the
   data itself.

Once populated, a consumer can start from the warehouse and answer questions
like:

- which curated tables, dbt models, or LookML objects exist?
- which upstream system published this metadata?
- how should a table, model, metric, or dashboard be interpreted?
- who owns the data product?
- what provider-specific metadata is available to query next?

This makes Agents Schema a shared discovery layer at the warehouse boundary. It
is not an action interface, a replacement for source-native APIs, or the only
metadata surface a specialized tool should use. Tools that need full-fidelity
authoring context can still use source files, vendor APIs, or MCP servers; those
same tools can also read `AGENTS` when they need a common, queryable view of
published metadata.

`AGENTS.ROOT` is the entry point for generic discovery. Specialized consumers
can also query well-known extension tables directly when they already know the
shape they need.

Example workflows:

- [examples/workflows/dbt.yml](./examples/workflows/dbt.yml): dbt manifest
  already exists.
- [examples/workflows/dbt-with-parse.yml](./examples/workflows/dbt-with-parse.yml):
  workflow should run `dbt parse`.
- [examples/workflows/dbt-looker.yml](./examples/workflows/dbt-looker.yml): dbt
  and Looker in one workflow.

## Prerequisites

### Warehouse Credentials

Create one required GitHub Actions secret in the repository that calls these
workflows:

```text
WAREHOUSE_CREDENTIALS
```

Snowflake is the only supported destination today, with more destination support
coming soon. For Snowflake, the secret value can be JSON:

```json
{
  "type": "snowflake",
  "account": "abc123",
  "user": "AGENTS_SCHEMA_BOT",
  "password": "secret",
  "warehouse": "COMPUTE_WH",
  "database": "ANALYTICS",
  "role": "TRANSFORMER"
}
```

or YAML:

```yaml
type: snowflake
account: abc123
user: AGENTS_SCHEMA_BOT
password: secret
warehouse: COMPUTE_WH
database: ANALYTICS
role: TRANSFORMER
```

`role` is optional. For key-pair auth, use `private_key_path` and optional
`private_key_passphrase` instead of `password`.

The destination object configures where Agents Schema writes. It does not
rename the schema; ingestion writes to `AGENTS`. The destination user needs
permission to create or replace tables in that schema.

`WAREHOUSE_CREDENTIALS` is only the destination for writing `AGENTS`. If the
workflow needs to run dbt, the dbt adapter is selected from the dbt profile, not
from these destination credentials.

## Sync dbt

Use the dbt reusable workflow when the repository contains a dbt project.

### Use an Existing Manifest

If the repository already has `target/manifest.json`, the workflow only needs to
know where the dbt project lives:

```yaml
name: Agents Schema dbt

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  agents-schema-dbt:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.1
    with:
      dbt-project-dir: dbt_project
    secrets: inherit
```

The workflow looks for:

```text
<dbt project>/target/manifest.json
```

### Generate a Manifest with dbt Parse

If the manifest is missing, the workflow can run `dbt parse`. Add this optional
secret:

```text
DBT_PROFILES_YML
```

The value is the full contents of `profiles.yml`. Then pass the dbt profile
name:

```yaml
name: Agents Schema dbt

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  agents-schema-dbt:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.1
    with:
      dbt-project-dir: dbt_project
      dbt-profile-name: analytics
      dbt-target: prod
    secrets: inherit
```

`dbt-target` is optional. If omitted, the workflow uses the profile's `target`;
if the profile has only one output, it uses that output.

When `DBT_PROFILES_YML` is supplied, the workflow writes it to:

```text
$RUNNER_TEMP/agents-schema-dbt-profiles/profiles.yml
```

The workflow reads the selected dbt profile output `type` and installs the
matching dbt adapter. Today `snowflake` maps to `dbt-snowflake`.

### Run a Custom dbt Parse Command

For custom dbt setups, pass `dbt-parse-command`. If `DBT_PROFILES_YML` and
`dbt-profile-name` are also present, the workflow sets `DBT_ADAPTER_PACKAGE`
before running the custom command:

```yaml
jobs:
  agents-schema-dbt:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.1
    with:
      dbt-project-dir: dbt_project
      dbt-profile-name: analytics
      dbt-target: prod
      dbt-parse-command: |
        uvx --with "$DBT_ADAPTER_PACKAGE" dbt parse \
          --project-dir dbt_project \
          --profiles-dir "$RUNNER_TEMP/agents-schema-dbt-profiles" \
          --profile analytics \
          --target prod \
          --no-partial-parse
    secrets: inherit
```

If the manifest is missing and the workflow cannot run managed parse or a custom
parse command, it fails with an explicit error.

## Sync Looker

Use the Looker reusable workflow when the repository contains LookML files:

```yaml
name: Agents Schema Looker

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  agents-schema-looker:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-looker.yml@v0.0.1
    with:
      lookml-dir: lookml
    secrets: inherit
```

The workflow reads `*.lkml` files from `lookml-dir`.

## Sync Multiple Sources

Use separate reusable workflows in the same GitHub Actions workflow:

```yaml
name: Agents Schema dbt + Looker

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  agents-schema-dbt:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.1
    with:
      dbt-project-dir: dbt_project
    secrets: inherit

  agents-schema-looker:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-looker.yml@v0.0.1
    with:
      lookml-dir: lookml
    secrets: inherit
```

These jobs do not need to depend on each other unless your repository has its
own ordering requirement.

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

Pin exact tags in customer workflows:

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
