# OSI Setup

## Prerequisites

Configure the `WAREHOUSE_CREDENTIALS` GitHub Actions secret for your destination
warehouse. See [Warehouse Credentials](README.md#warehouse-credentials).

## Run the OSI Sync Workflow

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
    uses: fivetran/agents_schema/.github/workflows/agents-schema-osi.yml@v0.0.7
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
