# OSI Setup

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
    uses: dbt-labs/agents_schema/.github/workflows/agents-schema-osi.yml@v0
    with:
      osi-dir: osi
    secrets:
      WAREHOUSE_CREDENTIALS: ${{ secrets.WAREHOUSE_CREDENTIALS }}
```

`osi-dir` is required — set it to the directory that contains your `*.osi.yaml`
files. The example uses `osi`; change it to match your repository. With
`osi-dir: osi`, place OSI files here:

```text
osi/*.osi.yaml
```

### Using Workload Identity Federation

To authenticate with `WAREHOUSE_CREDENTIALS.auth_method: adc` instead of a BigQuery
service account key, grant the job `id-token: write` and pass the Workload Identity
Federation inputs:

```yaml
permissions:
  id-token: write
  contents: read

jobs:
  agents-schema-osi:
    uses: dbt-labs/agents_schema/.github/workflows/agents-schema-osi.yml@v0
    with:
      osi-dir: osi
      workload-identity-provider: "projects/123/locations/global/workloadIdentityPools/my-pool/providers/my-provider"
      service-account: "agents-schema@my-gcp-project.iam.gserviceaccount.com"
    secrets:
      WAREHOUSE_CREDENTIALS: ${{ secrets.WAREHOUSE_CREDENTIALS }}
```

`WAREHOUSE_CREDENTIALS` still needs `type: bigquery`, `project_id`, and
`auth_method: adc` (see the BigQuery setup details above); it just no longer needs
a service account key.

Each `*.osi.yaml` file is validated against the vendored OSI JSON schema before
ingest; an invalid file fails the run with the offending path rather than writing
partial data.

The workflow writes:

- `AGENTS.OSI_MODEL`
- `AGENTS.OSI_DATASET`
- `AGENTS.OSI_FIELD`
- `AGENTS.OSI_METRIC`
- `AGENTS.OSI_RELATIONSHIP`

These jobs do not need to depend on dbt or Looker jobs unless your repository
has its own ordering requirement.
