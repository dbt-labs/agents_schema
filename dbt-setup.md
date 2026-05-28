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

Use the dbt workflow when the repository contains a dbt project.

#### Use an Existing Manifest

If the repository already has `target/manifest.json`, the workflow only needs to
know where the dbt project lives:

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

#### Generate a Manifest with dbt Parse

If the manifest is missing, the workflow can run `dbt parse`. Add this optional
secret:

```text
DBT_PROFILES_YML
```

The value is the full contents of `profiles.yml`. Then pass the dbt profile
name:

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
      dbt-profile-name: analytics
      dbt-target: prod
    secrets: inherit
```

`dbt-target` is optional. If omitted, the workflow uses the profile's `target`;
if the profile has only one output, it uses that output.

When `DBT_PROFILES_YML` is supplied, the workflow writes it to:

```text
$RUNNER_TEMP/agents-schema-dbt-profiles/profiles.yml
```

The workflow reads the selected dbt profile output `type` and installs the
matching dbt adapter. Today `snowflake` maps to `dbt-snowflake`.

#### Run a Custom dbt Parse Command

For custom dbt setups, pass `dbt-parse-command`. If `DBT_PROFILES_YML` and
`dbt-profile-name` are also present, the workflow sets `DBT_ADAPTER_PACKAGE`
before running the custom command:

```yaml
jobs:
  agents-schema-dbt:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.4
    with:
      dbt-project-dir: dbt_project
      dbt-profile-name: analytics
      dbt-target: prod
      dbt-parse-command: |
        uvx --with "$DBT_ADAPTER_PACKAGE" dbt parse \
          --project-dir dbt_project \
          --profiles-dir "$RUNNER_TEMP/agents-schema-dbt-profiles" \
          --profile analytics \
          --target prod \
          --no-partial-parse
    secrets: inherit
```

If the manifest is missing and the workflow cannot run managed parse or a custom
parse command, it fails with an explicit error.
