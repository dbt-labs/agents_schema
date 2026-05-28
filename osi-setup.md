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

### Sync OSI

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
    uses: fivetran/agents_schema/.github/workflows/agents-schema-osi.yml@v0.0.5
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
