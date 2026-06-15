# Looker Setup

## Prerequisites

The workflow needs destination warehouse credentials so it can create and
replace tables in the `AGENTS` schema.

Create one required GitHub Actions secret in the repository that calls these
workflows: `WAREHOUSE_CREDENTIALS`.

Snowflake and Databricks are supported destinations. The `type` field in the
secret selects the destination.

### Snowflake

We recommend key-pair authentication:

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

### Databricks

Authenticate with a personal access token against a SQL warehouse or cluster.

**Example Databricks secret:**

```yaml
type: databricks
server_hostname: dbc-12345678-90ab.cloud.databricks.com
http_path: /sql/1.0/warehouses/abc123def456
access_token: <your-databricks-personal-access-token>
catalog: analytics   # optional; sets the Unity Catalog catalog for the AGENTS schema
```

**Note:** `catalog` is optional; when omitted, the connection's default catalog is used.

## Run the Looker Sync Workflow

Use the Looker workflow when the repository contains LookML files:

```yaml
name: Agents Schema Looker

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  agents-schema-looker:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-looker.yml@v0.0.7
    with:
      lookml-dir: lookml
    secrets: inherit
```

`lookml-dir` is required — set it to the directory that contains your `*.lkml`
files. The example uses `lookml`; change it to match your repository.

These jobs do not need to depend on each other unless your repository has its
own ordering requirement.
