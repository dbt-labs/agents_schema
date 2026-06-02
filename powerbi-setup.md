# Power BI Setup

## Prerequisites

The workflow needs destination warehouse credentials so it can create and
replace tables in the `AGENTS` schema.

Create one required GitHub Actions secret in the repository that calls these
workflows: `WAREHOUSE_CREDENTIALS`.

Snowflake is the only supported destination today, with more destination
support coming soon. We recommend key-pair authentication:

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

## Run the Power BI Sync Workflow

Use the Power BI workflow when your repository contains a Fabric / Power BI scanner export.

```yaml
name: Agents Schema Power BI

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  agents-schema-powerbi:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-powerbi.yml@v0.0.6
    with:
      metadata-path: metadata/powerbi-scan.json
    secrets: inherit
```

`metadata-path` is required; set it to a file or directory containing JSON or YAML export files from the Fabric / Power BI scanner APIs.
The example uses `metadata/powerbi-scan.json`; change it to match your repository.

The CLI accepts a single `.json`, `.yaml`, or `.yml` file, or a directory tree
containing those files.

The workflow writes:

- `AGENTS.POWERBI_WORKSPACE`
- `AGENTS.POWERBI_SEMANTIC_MODEL`
- `AGENTS.POWERBI_TABLE`
- `AGENTS.POWERBI_COLUMN`
- `AGENTS.POWERBI_MEASURE`
- `AGENTS.POWERBI_REPORT`
- `AGENTS.POWERBI_LINEAGE`

This job does not need to depend on other Agents Schema jobs unless your repository has its
own ordering requirement.
