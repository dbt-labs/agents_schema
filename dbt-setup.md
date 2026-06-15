# dbt Setup

## Prerequisites

Configure the `WAREHOUSE_CREDENTIALS` GitHub Actions secret for your destination
warehouse. See [Warehouse Credentials](warehouse-credentials.md).

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
    uses: fivetran/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.7
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
