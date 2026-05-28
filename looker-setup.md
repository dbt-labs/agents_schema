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

### Sync Looker

Use the Looker workflow when the repository contains LookML files:

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

The workflow reads `*.lkml` files from `lookml-dir`.

These jobs do not need to depend on each other unless your repository has its
own ordering requirement.
