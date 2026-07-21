# BigQuery

Use the `bq` CLI.

1. Ask the user for their Google Cloud project ID unless they already supplied it in the same
   request. Read the optional `location` from `agents.yml` when present; otherwise ask for it only
   when the connection requires a specific location.
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
