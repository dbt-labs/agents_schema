# Tableau Setup

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

## Run the Tableau Sync Workflow

Use the Tableau workflow when your repository contains a Tableau Metadata API export.

```yaml
name: Agents Schema Tableau

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  agents-schema-tableau:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-tableau.yml@v0.0.6
    with:
      metadata-path: metadata/tableau-metadata.json
    secrets: inherit
```

`metadata-path` is required; set it to a file or directory containing JSON or YAML export files from Tableau Metadata API queries.
The example uses `metadata/tableau-metadata.json`; change it to match your repository.

The CLI accepts a single `.json`, `.yaml`, or `.yml` file, or a directory tree
containing those files.

The workflow writes:

- `AGENTS.TABLEAU_WORKBOOK`
- `AGENTS.TABLEAU_DATASOURCE`
- `AGENTS.TABLEAU_FIELD`
- `AGENTS.TABLEAU_DASHBOARD`
- `AGENTS.TABLEAU_LINEAGE`

This job does not need to depend on other Agents Schema jobs unless your repository has its
own ordering requirement.
