# Looker Setup

## Prerequisites

Configure the `WAREHOUSE_CREDENTIALS` GitHub Actions secret for your destination
warehouse. See [Warehouse Credentials](warehouse-credentials.md).

## Run the Looker Sync Workflow

Use the Looker workflow when the repository contains LookML files:

```yaml
name: Agents Schema Looker

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  agents-schema-looker:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-looker.yml@v0.0.7
    with:
      lookml-dir: lookml
    secrets: inherit
```

`lookml-dir` is required — set it to the directory that contains your `*.lkml`
files. The example uses `lookml`; change it to match your repository.

These jobs do not need to depend on each other unless your repository has its
own ordering requirement.
