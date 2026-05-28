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

### Sync Multiple Sources

Run the workflows from the same workflow file:

```yaml
name: Agents Schema dbt + Looker

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

  agents-schema-looker:
    uses: fivetran/agents_schema/.github/workflows/agents-schema-looker.yml@v0.0.4
    with:
      lookml-dir: lookml
    secrets: inherit
```

These jobs do not need to depend on each other unless your repository has its
own ordering requirement.
