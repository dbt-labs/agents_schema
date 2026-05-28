# Agents Schema

Agents need context to answer questions about warehouse data. Agents Schema puts
that context in the warehouse itself, in a standard `AGENTS` schema, so agents
can query metadata next to the data they are reasoning over. See
[Why Agents Schema](#why-agents-schema) for more on the idea behind it and
[SPEC.md](./SPEC.md) for the schema contract.

This repository provides GitHub workflows that ingest source metadata from
your repository and publish it into `AGENTS`.

![Agents Schema overview](assets/agents-schema-overview.png)

## Contents

- [Getting Started](#getting-started)
  - [Supported Metadata Sources](#supported-metadata-sources)
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

### Supported Metadata Sources

- dbt: reads `target/manifest.json` and writes `AGENTS.DBT_*` tables.
- Looker: reads `*.lkml` files and writes `AGENTS.LOOKML_*` tables.

More sources coming soon.

### Prerequisites

You need:

- A repository on GitHub that contains your dbt project or LookML files.
- A Snowflake user the workflows can connect with. The user needs permission
  to create or replace tables in the `AGENTS` schema (the schema name is
  fixed).

#### Add the WAREHOUSE_CREDENTIALS secret

The workflows read warehouse credentials from a repository secret named
`WAREHOUSE_CREDENTIALS`. To create it:

1. On GitHub, open the repository that will run the workflows.
2. Click **Settings** at the top of the repository page.
3. In the left sidebar, click **Secrets and variables** → **Actions**.
4. On the **Secrets** tab, scroll to **Repository secrets** and click
   **New repository secret**. (Use this, not the **Environments** tab —
   the workflows expect a repository-level secret.)
5. Set **Name** to `WAREHOUSE_CREDENTIALS`.
6. Paste one of the YAML values below into **Secret**, then click
   **Add secret**.

Snowflake is the only supported destination today, with more destination
support coming soon. The secret value is a YAML or JSON object. Choose one of
the two auth methods:

**Password auth:**

```yaml
type: snowflake
account: abc123
user: AGENTS_SCHEMA_BOT
warehouse: COMPUTE_WH
database: ANALYTICS
role: TRANSFORMER
password: secret
```

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

> **Pasting tip:** the `|` after `private_key_pem:` tells YAML to read the
> next indented block as a multi-line string. Every line of the PEM must be
> indented two spaces under it. If you copy the YAML directly from a file or
> editor, the indentation is preserved automatically; if you retype it,
> double-check the indent.

`role` is optional. An unencrypted key uses `-----BEGIN PRIVATE KEY-----` /
`-----END PRIVATE KEY-----` markers (without `ENCRYPTED`) and omits
`private_key_passphrase`. JSON works with the same field names.

New to Snowflake key-pair authentication? See
[Snowflake's key-pair authentication docs](https://docs.snowflake.com/en/user-guide/key-pair-auth)
for generating a key pair and registering the public key with your Snowflake
user.

`WAREHOUSE_CREDENTIALS` is only the destination for writing `AGENTS`. If the
workflow needs to run dbt, the dbt adapter is selected from the dbt profile, not
from these destination credentials.

## Guides

### Sync dbt

Use this workflow when your repository contains a dbt project.

#### Use an Existing Manifest

The simplest setup. Your repository already has a committed
`target/manifest.json` and the workflow just needs to know where the dbt
project lives.

**1. Add the workflow file**

1. On GitHub, open your repository.
2. Click the **Actions** tab.
3. If this is your first workflow, click **set up a workflow yourself**.
   Otherwise click **New workflow** → **set up a workflow yourself**.
4. Replace the file name at the top of the editor with
   `agents-schema-dbt.yml`.
5. Paste this into the editor (change `dbt_project` if your dbt project lives
   elsewhere):

   ```yaml
   name: Agents Schema dbt

   on:
     workflow_dispatch:
     push:
       branches: [main]

   jobs:
     agents-schema-dbt:
       uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.4
       with:
         dbt-project-dir: dbt_project
       secrets: inherit
   ```

6. Click **Commit changes**, then **Commit changes** in the dialog. GitHub
   creates the file at `.github/workflows/agents-schema-dbt.yml` on the
   default branch.

The workflow looks for `<dbt project>/target/manifest.json`.

**2. Trigger the workflow**

The two `on:` keys control when the workflow runs:

- `workflow_dispatch` exposes a **Run workflow** button in the Actions tab.
- `push: branches: [main]` runs it automatically on every push to `main`.

To run it manually right now: **Actions** tab → click **Agents Schema dbt** in
the left sidebar → **Run workflow** dropdown → **Run workflow**.

**3. Verify it worked**

- In the **Actions** tab, open the most recent run. A green checkmark means
  it succeeded; click any step to expand its logs.
- In Snowflake, confirm the tables exist:

  ```sql
  SELECT * FROM AGENTS.ROOT;
  SELECT * FROM AGENTS.DBT_MODEL LIMIT 10;
  ```

#### Generate a Manifest with dbt Parse

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
    uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.4
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

#### Run a Custom dbt Parse Command

For custom dbt setups, pass `dbt-parse-command`. If `DBT_PROFILES_YML` and
`dbt-profile-name` are also present, the workflow sets `DBT_ADAPTER_PACKAGE`
before running the custom command:

```yaml
jobs:
  agents-schema-dbt:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.4
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

### Sync Looker

Use this workflow when your repository contains LookML files.

**1. Add the workflow file**

1. On GitHub, open your repository.
2. Click the **Actions** tab.
3. If this is your first workflow, click **set up a workflow yourself**.
   Otherwise click **New workflow** → **set up a workflow yourself**.
4. Replace the file name at the top of the editor with
   `agents-schema-looker.yml`.
5. Paste this into the editor (change `lookml` if your LookML files live
   elsewhere):

   ```yaml
   name: Agents Schema Looker

   on:
     workflow_dispatch:
     push:
       branches: [main]

   jobs:
     agents-schema-looker:
       uses: fivetran/agents_schema/.github/workflows/agents-schema-looker.yml@v0.0.4
       with:
         lookml-dir: lookml
       secrets: inherit
   ```

6. Click **Commit changes**, then **Commit changes** in the dialog. GitHub
   creates the file at `.github/workflows/agents-schema-looker.yml` on the
   default branch.

The workflow reads `*.lkml` files from `lookml-dir`.

**2. Trigger the workflow**

Same as the dbt flow: `workflow_dispatch` adds a manual **Run workflow**
button; `push: branches: [main]` runs it automatically on every push to
`main`.

To run it manually right now: **Actions** tab → click **Agents Schema Looker**
in the left sidebar → **Run workflow** dropdown → **Run workflow**.

**3. Verify it worked**

- In the **Actions** tab, the most recent run should show a green checkmark.
  Click any step to expand its logs.
- In Snowflake:

  ```sql
  SELECT * FROM AGENTS.ROOT;
  SELECT * FROM AGENTS.LOOKML_VIEW LIMIT 10;
  ```

### Sync Multiple Sources

To run both workflows from one file, follow the same "Add the workflow file"
steps from [Sync dbt](#sync-dbt) but use this YAML and name the file
something like `agents-schema.yml`:

```yaml
name: Agents Schema dbt + Looker

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  agents-schema-dbt:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.4
    with:
      dbt-project-dir: dbt_project
    secrets: inherit

  agents-schema-looker:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-looker.yml@v0.0.4
    with:
      lookml-dir: lookml
    secrets: inherit
```

These jobs do not need to depend on each other unless your repository has its
own ordering requirement. The single `WAREHOUSE_CREDENTIALS` secret you
created in [Prerequisites](#prerequisites) covers both.

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
