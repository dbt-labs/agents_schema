# BigQuery

Use the `bq` CLI.

1. Read `project_id` and optional `location` from `agents.yml` when present. Otherwise ask the
   user which Google Cloud project and location to use.
2. If authentication is missing, help the user authenticate the Google Cloud CLI.
3. Verify the connection:

   ```bash
   bq query \
     --project_id="<project_id>" \
     --location="<location>" \
     --use_legacy_sql=false \
     'SELECT 1'
   ```

Omit `--location` when it is not configured. Run later SQL by replacing `<SQL>` below:

```bash
bq query \
  --project_id="<project_id>" \
  --location="<location>" \
  --use_legacy_sql=false \
  --format=json <<'SQLEOF'
<SQL>
SQLEOF
```
