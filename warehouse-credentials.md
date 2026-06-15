# Warehouse Credentials

Agents Schema workflows write to your warehouse using one GitHub Actions secret:
`WAREHOUSE_CREDENTIALS`.

Supported destinations:

| Destination | `type` | Authentication |
| --- | --- | --- |
| Snowflake | `snowflake` | Password or key-pair auth |
| Databricks | `databricks` | Personal access token |
| BigQuery | `bigquery` | Service account JSON |

## Snowflake

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

## Databricks

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

## BigQuery

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
