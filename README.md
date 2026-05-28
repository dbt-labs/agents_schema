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

For Snowflake, the secret value can be JSON:

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
rename the schema; ingestion writes to `AGENTS`. The Snowflake user needs
permission to create or replace tables in that schema.

For dbt, add this optional secret if your repo does not check in a
`profiles.yml` and the workflow needs to create a manifest:

```text
DBT_PROFILES_YML
```

The value is the full contents of `profiles.yml`.

## dbt

Customer workflow:

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
      dbt-adapter: dbt-snowflake
    secrets: inherit
```

The dbt workflow expects a manifest at:

```text
<dbt project>/target/manifest.json
```

If the manifest is missing, the workflow creates it with `dbt parse`. To do
that, it needs a dbt profile. It uses `DBT_PROFILES_YML` when that secret is
present. Otherwise it looks for `profiles.yml` in `dbt-project-dir`. If neither
exists, the workflow fails with an explicit error.

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
      dbt-adapter: dbt-snowflake
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
