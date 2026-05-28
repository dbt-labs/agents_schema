# Agents Schema

Agents Schema publishes metadata into a standard `AGENTS` schema in your
warehouse. The first supported customer paths are dbt and Looker:

- dbt ingestion reads `target/manifest.json` and writes `AGENTS.DBT_*` tables.
- Looker ingestion reads `*.lkml` files and writes `AGENTS.LOOKML_*` tables.

This repository contains:

- reusable workflows that customers call from their own repositories
- source-specific GitHub Actions used by those workflows
- the Python CLI used by those actions
- the schema specification in [SPEC.md](./SPEC.md)

The package is not published to PyPI yet. The actions run it with `uv` from the
public GitHub repository at the pinned version.

## Warehouse Credentials Secret

Create one required GitHub Actions secret in the customer repository:

```text
WAREHOUSE_CREDENTIALS
```

Snowflake is the only supported destination today, with more destination support coming soon. For Snowflake, the secret
value can be JSON:

```json
{
  "type": "snowflake",
  "account": "abc123",
  "user": "AGENTS_SCHEMA_BOT",
  "password": "secret",
  "warehouse": "COMPUTE_WH",
  "database": "ANALYTICS",
  "role": "TRANSFORMER"
}
```

or YAML:

```yaml
type: snowflake
account: abc123
user: AGENTS_SCHEMA_BOT
password: secret
warehouse: COMPUTE_WH
database: ANALYTICS
role: TRANSFORMER
```

`role` is optional. For key-pair auth, use `private_key_path` and optional
`private_key_passphrase` instead of `password`.

The destination object configures how to connect to the warehouse. It does not
rename the schema; ingestion writes to `AGENTS`. The destination user needs
permission to create or replace tables in that schema.

`WAREHOUSE_CREDENTIALS` is only the destination for writing `AGENTS`. If the
workflow needs to run dbt, the dbt adapter is selected from the dbt profile, not
from these destination credentials.

For dbt, add this optional secret if your repo does not check in a
`target/manifest.json` and the workflow needs to run `dbt parse`:

```text
DBT_PROFILES_YML
```

Create it as a repository or organization Actions secret. The value is the full
contents of `profiles.yml`.

## dbt

If the customer repo already has `target/manifest.json`, the workflow only
needs to know where the dbt project lives:

```yaml
name: Agents Schema dbt

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  agents-schema-dbt:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.1
    with:
      dbt-project-dir: dbt_project
    secrets: inherit
```

The dbt workflow expects a manifest at:

```text
<dbt project>/target/manifest.json
```

If the manifest is missing, the workflow can run `dbt parse` when you provide
enough dbt profile information. In that mode, these are required:

- `DBT_PROFILES_YML` secret containing the full `profiles.yml`
- `dbt-profile-name` input selecting the profile inside that file

`dbt-target` is optional. If omitted, the workflow uses the profile's `target`;
if the profile has only one output, it uses that output.

```yaml
name: Agents Schema dbt

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  agents-schema-dbt:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.1
    with:
      dbt-project-dir: dbt_project
      dbt-profile-name: analytics
      dbt-target: prod
    secrets: inherit
```

When `DBT_PROFILES_YML` is supplied, the workflow writes it to:

```text
$RUNNER_TEMP/agents-schema-dbt-profiles/profiles.yml
```

Managed parse uses that directory automatically. Custom parse commands should
point to it with `--profiles-dir`.

The workflow reads the selected dbt profile output `type` and installs the
matching dbt adapter. Today `snowflake` maps to `dbt-snowflake`.

For custom dbt setups, pass `dbt-parse-command` instead. If `DBT_PROFILES_YML`
and `dbt-profile-name` are also present, the workflow sets
`DBT_ADAPTER_PACKAGE` before running the custom command:

```yaml
jobs:
  agents-schema-dbt:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.1
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

If the manifest is missing and the workflow cannot run either managed parse or
the custom command, it fails with an explicit error.

## dbt + Looker

Customer workflow:

```yaml
name: Agents Schema dbt + Looker

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  agents-schema-dbt:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.1
    with:
      dbt-project-dir: dbt_project
    secrets: inherit

  agents-schema-looker:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-looker.yml@v0.0.1
    with:
      lookml-dir: lookml
    secrets: inherit
```

The Looker workflow reads `*.lkml` files from the configured `lookml-dir`.

## CLI

The GitHub Actions call the CLI with explicit source arguments:

```bash
agents-schema dbt --project-dir dbt_project
agents-schema looker --lookml-dir lookml
```

The CLI reads warehouse credentials from `WAREHOUSE_CREDENTIALS`.

## Versioning

Release tags version the whole repository: reusable workflows, actions, CLI
source, examples, README, and spec.

Pin exact tags in customer workflows:

```yaml
uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.1
```

To upgrade, change only the tag:

```diff
- uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.1
+ uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.2
```

## Specification

The full schema contract is in [SPEC.md](./SPEC.md). Keep schema definitions and
compatibility rules there; keep this README focused on installation and the
source-specific ingestion workflows.
