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

### Sync dbt

In your dbt project repository, set up a new GitHub Workflow from the Actions tab. 

There are three cases:
1. Use an Existing Manifest: If your project already has a manifest.json file, use this approach.
2. Generate a Manifest with dbt Parse
3. Run a Custom dbt Parse Command

#### Use an Existing Manifest

NOTE: Requires a dbt `manifest.json` file. If you don't have an existing manifest, produce it and check it into your dbt project's repository.

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

The workflow looks for:

```text
<dbt project>/target/manifest.json
```
