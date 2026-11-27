# dbt Setup

## Prerequisites

Configure the `WAREHOUSE_CREDENTIALS` GitHub Actions secret for your destination
warehouse. Copy the YAML for your destination, fill in your values, and save it
as the `WAREHOUSE_CREDENTIALS` GitHub Actions secret in the repository that
calls this workflow.

<details>
<summary>Snowflake setup</summary>

We recommend key-pair authentication:

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
`-----END PRIVATE KEY-----` markers and omits `private_key_passphrase`.

Password auth is also supported by replacing the private key fields with:

```yaml
password: your-password
```

</details>

<details>
<summary>Databricks setup</summary>

Use a SQL warehouse HTTP path and a personal access token:

```yaml
type: databricks
host: dbc-abc123.cloud.databricks.com
http_path: /sql/1.0/warehouses/abc123
catalog: main
token: your-personal-access-token
```

The token needs permission to create and write tables in the `agents` schema
within the configured catalog.

</details>

<details>
<summary>BigQuery setup</summary>

Use the destination project plus a service account JSON object:

```yaml
type: bigquery
project_id: my-gcp-project
location: US
credentials_json:
  type: service_account
  project_id: service-account-project
  private_key_id: ...
  private_key: |
    -----BEGIN PRIVATE KEY-----
    ...
    -----END PRIVATE KEY-----
  client_email: agents-schema@my-gcp-project.iam.gserviceaccount.com
  client_id: ...
  auth_uri: https://accounts.google.com/o/oauth2/auth
  token_uri: https://oauth2.googleapis.com/token
  auth_provider_x509_cert_url: https://www.googleapis.com/oauth2/v1/certs
  client_x509_cert_url: ...
```

`location` is optional. The service account needs permission to create datasets
and create, load, query, update, and delete tables in the destination project.

Alternatively, use Application Default Credentials (ADC) instead of a static
key — for example with GitHub Actions Workload Identity Federation via
[`google-github-actions/auth@v2`](https://github.com/google-github-actions/auth),
which requires no long-lived secret:

```yaml
type: bigquery
project_id: my-gcp-project
location: US
auth_method: adc
```

The step that runs before this one must leave Application Default Credentials
resolvable in the environment. `google-github-actions/auth` with
`workload_identity_provider` and `service_account` inputs sets
`GOOGLE_APPLICATION_CREDENTIALS` to a short-lived credential file, which
`google.auth.default()` picks up automatically. The impersonated service
account needs the same dataset/table permissions listed above.

</details>

<details>
<summary>ClickHouse setup</summary>

Use the HTTP interface host plus a user with rights on the `agents` database:

```yaml
type: clickhouse
host: abc123.region.clickhouse.cloud
port: 8443
user: agents_schema_bot
password: your-password
secure: true
```

See [clickhouse-setup.md](clickhouse-setup.md) for grants, type mapping, and
replicated-cluster notes. Managed dbt parse supports profiles with
`type: clickhouse` (the [dbt-clickhouse](https://github.com/ClickHouse/dbt-clickhouse)
adapter).

</details>

## Run the dbt Sync Workflow

In your dbt project repository, set up a new GitHub Workflow from the Actions tab. 

The workflow needs a dbt manifest at `<dbt project>/target/manifest.json`. It finds or creates one in
this order:

1. **An existing manifest.** If the file is already in the repository checkout when the workflow runs
   (that is, committed), it is used as is. The workflow runs in its own job, so a manifest produced by
   another job of your workflow is not available to it.
2. **A custom parse command.** If `dbt-parse-command` is set, the workflow runs it to create the manifest.
3. **Managed parse.** If the `DBT_PROFILES_YML` secret and `dbt-profile-name` are set, the workflow runs
   `dbt deps` (when the project has a `packages.yml` or `dependencies.yml`) and `dbt parse` for you.
   See [Generating the manifest in the workflow](#generating-the-manifest-in-the-workflow).

If none of these applies, the job fails with an error that lists the options. The example below uses
an existing manifest.

```yaml
name: Agents Schema dbt

on:
  workflow_dispatch:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write

jobs:
  agents-schema-dbt:
    uses: dbt-labs/agents_schema/.github/workflows/agents-schema-dbt.yml@v0
    with:
      dbt-project-dir: dbt_project
    secrets:
      WAREHOUSE_CREDENTIALS: ${{ secrets.WAREHOUSE_CREDENTIALS }}
```

Grant `contents: read` and `id-token: write` in the calling workflow, as shown. The reusable
workflows use `id-token: write` for the optional Workload Identity Federation described below,
and GitHub does not start a called workflow that requests more permission than its caller
grants, so include it even if you do not use that option.

`dbt-project-dir` is required — set it to the path of your dbt project (the
directory that contains `dbt_project.yml`). The example uses `dbt_project`;
change it to match your repository.

The workflow looks for:

```text
<dbt project>/target/manifest.json
```

### Generating the manifest in the workflow

To have the workflow run `dbt parse` instead of committing `target/manifest.json`, store the contents
of a dbt `profiles.yml` in a `DBT_PROFILES_YML` repository secret and name the profile:

```yaml
permissions:
  contents: read
  id-token: write

jobs:
  agents-schema-dbt:
    uses: dbt-labs/agents_schema/.github/workflows/agents-schema-dbt.yml@v0
    with:
      dbt-project-dir: dbt_project
      dbt-profile-name: analytics
      dbt-target: prod
    secrets:
      WAREHOUSE_CREDENTIALS: ${{ secrets.WAREHOUSE_CREDENTIALS }}
      DBT_PROFILES_YML: ${{ secrets.DBT_PROFILES_YML }}
```

- `dbt-profile-name` selects the profile. `dbt-target` is optional: it defaults to the profile's
  `target`, or to its only output.
- The adapter package is chosen from the target's `type`: `bigquery` uses `dbt-bigquery`, `clickhouse`
  uses `dbt-clickhouse`, `databricks` uses `dbt-databricks`, and `snowflake` uses `dbt-snowflake`. Any
  other type is rejected.
- Managed parse runs `dbt-core` 1.x with that adapter (these adapters require `dbt-core<2`). A manifest
  that already exists always wins, so remove the committed one if you want the workflow to regenerate it.
- To use a different command, set `dbt-parse-command`. It takes precedence over managed parse and runs
  with `bash` from the repository root, so it must write `<dbt-project-dir>/target/manifest.json`: pass
  `--project-dir` (for `dbt-project-dir: dbt_project`, use `--project-dir dbt_project`). When
  `DBT_PROFILES_YML` is set, it is written to `$RUNNER_TEMP/agents-schema-dbt-profiles/profiles.yml`
  before the command runs, so `--profiles-dir "$RUNNER_TEMP/agents-schema-dbt-profiles"` finds it. If you
  also set `dbt-profile-name`, the profile is validated first (its `type` must be one of the four above)
  and the matching adapter package is exported as `DBT_ADAPTER_PACKAGE`. Leave `dbt-profile-name` unset
  to skip that validation, for example to use an adapter that is not in the list.

#### Manifests from dbt 2

You can generate the manifest with dbt 2 (the `dbt` package on PyPI, a Rust-based engine) by using
`dbt-parse-command`, and the workflow ingests it:

```yaml
permissions:
  contents: read
  id-token: write

jobs:
  agents-schema-dbt:
    uses: dbt-labs/agents_schema/.github/workflows/agents-schema-dbt.yml@v0
    with:
      dbt-project-dir: dbt_project
      dbt-parse-command: >-
        uvx --from "dbt==2.0.13" dbt parse --project-dir dbt_project
        --profiles-dir "$RUNNER_TEMP/agents-schema-dbt-profiles" --no-partial-parse
    secrets:
      WAREHOUSE_CREDENTIALS: ${{ secrets.WAREHOUSE_CREDENTIALS }}
      DBT_PROFILES_YML: ${{ secrets.DBT_PROFILES_YML }}
```

Agents Schema reads the same manifest fields from both. On a sample project, dbt 2.0.13 and dbt-core 1.12.7 produced identical
`AGENTS.DBT_*` rows with BigQuery, Snowflake, Databricks, ClickHouse, and DuckDB profiles. One
difference to know about: dbt 2 requires `meta` under `config:`. A top-level `meta:` key on a model
or column is an error (`dbt parse` exits with status 1), and the value is left out of the manifest,
so it does not reach `meta` in `AGENTS.DBT_MODEL` or `AGENTS.DBT_COLUMN`.

### Using Workload Identity Federation

To authenticate with `WAREHOUSE_CREDENTIALS.auth_method: adc` instead of a BigQuery
service account key, grant the job `id-token: write` and pass the Workload Identity
Federation inputs:

```yaml
permissions:
  id-token: write
  contents: read

jobs:
  agents-schema-dbt:
    uses: dbt-labs/agents_schema/.github/workflows/agents-schema-dbt.yml@v0
    with:
      dbt-project-dir: dbt_project
      workload-identity-provider: "projects/123/locations/global/workloadIdentityPools/my-pool/providers/my-provider"
      service-account: "agents-schema@my-gcp-project.iam.gserviceaccount.com"
    secrets:
      WAREHOUSE_CREDENTIALS: ${{ secrets.WAREHOUSE_CREDENTIALS }}
```

`WAREHOUSE_CREDENTIALS` still needs `type: bigquery`, `project_id`, and
`auth_method: adc` (see the BigQuery setup details above); it just no longer needs
a service account key.
