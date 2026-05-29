# dbt Setup

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

## Run the dbt Sync Workflow

In your dbt project repository, set up a new GitHub Workflow from the Actions tab. 

NOTE: Requires a dbt `manifest.json` file. If you don't have an existing manifest, produce it and check it into your dbt project's repository.

```yaml
name: Agents Schema dbt

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  agents-schema-dbt:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.6
    with:
      dbt-project-dir: dbt_project
    secrets: inherit
```

`dbt-project-dir` is required — set it to the path of your dbt project (the
directory that contains `dbt_project.yml`). The example uses `dbt_project`;
change it to match your repository.

The workflow looks for:

```text
<dbt project>/target/manifest.json
```
