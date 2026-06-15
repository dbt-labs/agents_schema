# OSI Setup

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

## Run the OSI Sync Workflow

Use the OSI workflow when the repository contains Open Semantic Interchange
YAML files:

```yaml
name: Agents Schema OSI

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  agents-schema-osi:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-osi.yml@v0.0.7
    with:
      osi-dir: osi
    secrets: inherit
```

`osi-dir` is required — set it to the directory that contains your `*.osi.yaml`
files. The example uses `osi`; change it to match your repository. With
`osi-dir: osi`, place OSI files here:

```text
osi/*.osi.yaml
```

The workflow writes:

- `AGENTS.OSI_DATASET`
- `AGENTS.OSI_FIELD`
- `AGENTS.OSI_METRIC`
- `AGENTS.OSI_RELATIONSHIP`

These jobs do not need to depend on dbt or Looker jobs unless your repository
has its own ordering requirement.
