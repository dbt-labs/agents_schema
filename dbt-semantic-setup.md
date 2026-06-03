# dbt Semantic Layer Setup

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

## Run the dbt Semantic Layer Sync Workflow

Use the dbt Semantic Layer workflow when your repository contains a dbt Semantic Layer semantic manifest.

```yaml
name: Agents Schema dbt Semantic Layer

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  agents-schema-dbt-semantic:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt-semantic.yml@v0.0.6
    with:
      semantic-manifest: target/semantic_manifest.json
    secrets: inherit
```

`semantic-manifest` is required; set it to a file or directory containing semantic_manifest.json or equivalent JSON/YAML semantic metadata exports.
The example uses `target/semantic_manifest.json`; change it to match your repository.

The CLI accepts a single `.json`, `.yaml`, or `.yml` file, or a directory tree
containing those files.

The workflow writes:

- `AGENTS.DBT_SEMANTIC_MODEL`
- `AGENTS.DBT_SEMANTIC_ENTITY`
- `AGENTS.DBT_SEMANTIC_DIMENSION`
- `AGENTS.DBT_SEMANTIC_MEASURE`
- `AGENTS.DBT_SEMANTIC_METRIC`

This job does not need to depend on other Agents Schema jobs unless your repository has its
own ordering requirement.
