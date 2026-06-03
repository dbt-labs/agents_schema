# Metabase Setup

## Prerequisites

The workflow needs destination warehouse credentials so it can create and
replace tables in the `AGENTS` schema.

Create one required GitHub Actions secret in the repository that calls these
workflows: `WAREHOUSE_CREDENTIALS`.

Snowflake is the production warehouse destination. DuckDB is also supported
for local validation runs. For Snowflake, we recommend key-pair authentication:

**Example key-pair auth secret:**

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

**Note:**
- `role` is optional.
- An unencrypted key uses `-----BEGIN PRIVATE KEY-----` / `-----END PRIVATE KEY-----` markers and omits `private_key_passphrase`.

## Run the Metabase Sync Workflow

Use the Metabase workflow when your repository contains Metabase API exports.

```yaml
name: Agents Schema Metabase

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  agents-schema-metabase:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-metabase.yml@v0.0.6
    with:
      metadata-path: metadata/metabase-export.json
    secrets: inherit
```

`metadata-path` is required; set it to a file or directory containing JSON or YAML exports from Metabase database, table, card, and dashboard APIs.
The example uses `metadata/metabase-export.json`; change it to match your repository.

The CLI accepts a single `.json`, `.yaml`, or `.yml` file, or a directory tree
containing those files.

The workflow writes:

- `AGENTS.METABASE_DATABASE`
- `AGENTS.METABASE_TABLE`
- `AGENTS.METABASE_FIELD`
- `AGENTS.METABASE_CARD`
- `AGENTS.METABASE_DASHBOARD`

This job does not need to depend on other Agents Schema jobs unless your repository has its
own ordering requirement.
